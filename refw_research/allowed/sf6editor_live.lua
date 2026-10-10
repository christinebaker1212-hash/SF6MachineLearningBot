-- SF6 Mod Editor — live preview companion for REFramework
--
-- Watches reframework/data/sf6editor/live.json (written by the editor) and
-- applies costume-colour edits to the fighters on screen (Training Mode is
-- the easiest place to use it).
--
-- How: each fighter model has an app.PlayerColorController. Its
-- ColorData.Colors list maps colour ids to the CostumeMaterialData the game
-- loaded from esfNNN_CCC_cmd_NNN.user.2. We write the edited values into
-- that live data (field by field, using the same paths as the editor), then
-- ask the controller to SetColor(id) again so the model is re-dressed.
-- The technique follows the open-source SF6 Color Mod (Wael3rd/SF6-ModSuite,
-- MIT). Originals are kept and restored with "Stop preview".
--
-- Animated colours: the payload's "anim" list is played here (colour data
-- itself can't change over time): every few frames the colours are worked
-- out and the fighters re-dressed. The preview (and its animations) is
-- applied again whenever the fighters on screen change (new round, new
-- match), until the editor sends "stop".
--
-- Payload:
-- {
--   "stamp": 123,
--   "side": "both" | "p1" | "p2",
--   "clusters": ["Cluster_Gi", ...],       -- only data whose clusters match is touched
--   "values": { "Parts/0/Clusters/1/CustomizeColors/0/Color": [r,g,b,a], ".../_Value": 0.5, ".../Enable": true },
--   "anim": [ { "path": ".../Color", "mode": "pulse" | "rainbow", "a": [r,g,b,a], "b": [r,g,b,a], "period": 2.0 } ],
--   "anim_every": 2                         -- frames between animation steps (optional)
-- }
-- or { "stamp": 124, "stop": true } to put the game's colours back,
-- or { "stamp": 125, "dump": true } to list the colour controllers in dump.json.
--
-- The SF6 bot's REFramework research build runs this file only if it is
-- byte-for-byte the copy it was built with (sf6machinelearningbot
-- refw_research/allowed/sf6editor_live.lua): change both together.

local LIVE_FILE = "sf6editor/live.json"
local DUMP_FILE = "sf6editor/dump.json"
local STATUS_FILE = "sf6editor/status.json"


local state = {
    enabled = true,
    last_stamp = nil,
    payload = nil,
    status = "waiting for the editor",
    frame = 0,
    check_every = 15,
    rescan_every = 60,
    anim_every = 2,
    saved = {},          -- { obj, off, kind, old, type }
    targets = {},        -- fighters the payload was applied to: { ctrl, data, num }
    signature = "",      -- which controllers are on screen (to notice new fighters)
}

-- tells the editor what happened with its last request
local function report(stamp, touched)
    pcall(json.dump_file, STATUS_FILE, { stamp = stamp, status = state.status, touched = touched or 0 })
end

local ctrl_type = nil

local function get_scene()
    local sm = sdk.get_native_singleton("via.SceneManager")
    if not sm then return nil end
    return sdk.call_native_func(sm, sdk.find_type_definition("via.SceneManager"), "get_CurrentScene")
end

local function controllers()
    local scene = get_scene()
    if not scene then return {} end
    ctrl_type = ctrl_type or sdk.typeof("app.PlayerColorController")
    if not ctrl_type then return {} end
    local arr = scene:call("findComponents(System.Type)", ctrl_type)
    if not arr then return {} end
    local ok, elems = pcall(function() return arr:get_elements() end)
    return ok and elems or {}
end

local function go_name(obj)
    local ok, n = pcall(function() return obj:call("get_GameObject"):call("get_Name") end)
    return ok and n or ""
end

local function type_name(obj)
    local ok, n = pcall(function() return obj:get_type_definition():get_full_name() end)
    return ok and n or nil
end

-- an object we touched earlier may be gone (a match ended): only write into
-- it while it is still a live object of the same type
local function still_valid(obj, tname)
    if type(sdk.is_managed_object) == "function" then
        local ok, live = pcall(sdk.is_managed_object, obj)
        if ok and not live then return false end
    end
    return tname == nil or type_name(obj) == tname
end

-- 1 = P1, 2 = P2, 3 = menu preview, 0 = unknown (parent names from the SF6 Color Mod)
local function side_of(ctrl)
    local ok, side = pcall(function()
        local t = ctrl:call("get_GameObject"):call("get_Transform")
        for _ = 1, 4 do
            local p = t:call("get_Parent")
            if not p then return 0 end
            local n = p:call("get_GameObject"):call("get_Name")
            if n == "FighterVisual_01" or n == "Left" then return 1 end
            if n == "FighterVisual_02" or n == "Right" then return 2 end
            if n == "FighterReady_BattleSetting" then return 3 end
            t = p
        end
        return 0
    end)
    return ok and side or 0
end

-- arrays (T[]) and List<T>
local function seq_len(o)
    if not o then return 0 end
    local ok, n = pcall(function() return o:get_size() end)
    if ok and n then return n end
    ok, n = pcall(function() return o:call("get_Count") end)
    return ok and n or 0
end
local function seq_at(o, i)
    local ok, v = pcall(function() return o:get_element(i) end)
    if ok and v then return v end
    ok, v = pcall(function() return o:call("get_Item", i) end)
    return ok and v or nil
end

local function current_data(ctrl)
    local num = ctrl:get_field("ColorNum")
    local cd = ctrl:get_field("ColorData")
    local colors = cd and cd:get_field("Colors")
    for i = 0, seq_len(colors) - 1 do
        local e = seq_at(colors, i)
        if e and e:get_field("ColorId") == num then return e:get_field("Data"), num end
    end
    return nil, num
end

local function cluster_names(data)
    local names = {}
    local parts = data:get_field("Parts")
    for p = 0, seq_len(parts) - 1 do
        local part = seq_at(parts, p)
        local clusters = part and part:get_field("Clusters")
        for c = 0, seq_len(clusters) - 1 do
            local cl = seq_at(clusters, c)
            local n = cl and cl:get_field("Name")
            if n then names[#names + 1] = tostring(n) end
        end
    end
    return names
end

local function matches(data, wanted)
    if not wanted or #wanted == 0 then return true end
    local have = {}
    for _, n in ipairs(cluster_names(data)) do have[n] = true end
    for _, n in ipairs(wanted) do if not have[n] then return false end end
    return true
end

-- field offset: plain name, auto-property backing field, or "_" cache (as the Color Mod does)
local function field_offsets(obj, name)
    local td = obj:get_type_definition()
    local out = {}
    for _, n in ipairs({ name, "<" .. name .. ">k__BackingField", "_" .. name }) do
        local t = td
        while t do
            local f = t:get_field(n)
            if f then
                local off = f:get_offset_from_base()
                local dup = false
                for _, o in ipairs(out) do if o == off then dup = true end end
                if not dup then out[#out + 1] = off end
                break
            end
            t = t:get_parent_type()
        end
    end
    return out
end

local function clamp_byte(x)
    x = math.floor((x or 0) + 0.5)
    if x < 0 then return 0 end
    if x > 255 then return 255 end
    return x
end

-- writes one field; `nosave` = don't remember the old value (animation steps:
-- the first, still write already saved the game's original)
local function write_value(obj, name, value, nosave)
    local offs = field_offsets(obj, name)
    local tname = (not nosave) and type_name(obj) or nil
    for _, off in ipairs(offs) do
        if type(value) == "boolean" then
            if not nosave then table.insert(state.saved, { obj = obj, off = off, kind = "b", old = obj:read_byte(off), type = tname }) end
            obj:write_byte(off, value and 1 or 0)
        elseif type(value) == "table" then
            local r, g, b, a = clamp_byte(value[1]), clamp_byte(value[2]), clamp_byte(value[3]), clamp_byte(value[4] or 255)
            if not nosave then table.insert(state.saved, { obj = obj, off = off, kind = "d", old = obj:read_dword(off), type = tname }) end
            obj:write_dword(off, ((a * 256 + b) * 256 + g) * 256 + r)
        elseif type(value) == "number" then
            if not nosave then table.insert(state.saved, { obj = obj, off = off, kind = "f", old = obj:read_float(off), type = tname }) end
            obj:write_float(off, value)
        end
    end
    return #offs
end

-- walk "Parts/0/Clusters/1/CustomizeColors/0/Color" through the live objects
local function apply_path(data, path, value, nosave)
    local segs = {}
    for s in string.gmatch(path, "[^/]+") do segs[#segs + 1] = s end
    local obj = data
    local i = 1
    while i < #segs do
        local child = obj:get_field(segs[i])
        local nxt = tonumber(segs[i + 1])
        if nxt ~= nil then
            child = seq_at(child, nxt)
            i = i + 2
        else
            i = i + 1
        end
        if not child then return 0 end
        obj = child
    end
    return write_value(obj, segs[#segs], value, nosave)
end

local function restore()
    for k = #state.saved, 1, -1 do
        local s = state.saved[k]
        if still_valid(s.obj, s.type) then
            pcall(function()
                if s.kind == "b" then s.obj:write_byte(s.off, s.old)
                elseif s.kind == "d" then s.obj:write_dword(s.off, s.old)
                else s.obj:write_float(s.off, s.old) end
            end)
        end
    end
    state.saved = {}
    state.targets = {}
end

-- which colour controllers are on screen, as one string (new fighters = new string)
local function signature(list)
    local parts = {}
    for _, ctrl in ipairs(list) do
        local ok, addr = pcall(function() return ctrl:get_address() end)
        parts[#parts + 1] = ok and tostring(addr) or "?"
    end
    table.sort(parts)
    return table.concat(parts, ",")
end

local function apply(payload)
    restore()
    local touched = 0
    local list = controllers()
    state.signature = signature(list)
    for _, ctrl in ipairs(list) do
        local side = side_of(ctrl)
        local want = payload.side or "both"
        local side_ok = want == "both" or (want == "p1" and (side == 1 or side == 3)) or (want == "p2" and side == 2)
        if side_ok then
            local data, num = current_data(ctrl)
            if data and matches(data, payload.clusters) then
                for path, value in pairs(payload.values or {}) do
                    pcall(apply_path, data, path, value)
                end
                pcall(function() ctrl:call("SetColor(System.Int32)", num) end)
                touched = touched + 1
                state.targets[#state.targets + 1] = { ctrl = ctrl, data = data, num = num, ctrl_type = type_name(ctrl), data_type = type_name(data) }
            end
        end
    end
    local animated = payload.anim and #payload.anim or 0
    state.status = touched > 0
        and string.format("colours applied to %d fighter model(s)%s", touched, animated > 0 and string.format(", %d animated", animated) or "")
        or "no matching fighter on screen - pick the same fighter, costume and colour in game"
    return touched
end

-- ---- animation ----------------------------------------------------------

local function rgb_to_hsv(r, g, b)
    local mx, mn = math.max(r, g, b), math.min(r, g, b)
    local d = mx - mn
    local h = 0
    if d > 0 then
        if mx == r then h = ((g - b) / d) % 6
        elseif mx == g then h = (b - r) / d + 2
        else h = (r - g) / d + 4 end
        h = h / 6
    end
    return h, (mx > 0) and d / mx or 0, mx
end

local function hsv_to_rgb(h, s, v)
    local i = math.floor(h * 6)
    local f = h * 6 - i
    local p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    i = i % 6
    if i == 0 then return v, t, p
    elseif i == 1 then return q, v, p
    elseif i == 2 then return p, v, t
    elseif i == 3 then return p, q, v
    elseif i == 4 then return t, p, v
    else return v, p, q end
end

-- colour of one animation at time t (seconds)
local function anim_color(a, t)
    local period = tonumber(a.period) or 2
    if period < 0.05 then period = 0.05 end
    local phase = (t % period) / period
    local A = a.a or { 255, 255, 255, 255 }
    if a.mode == "rainbow" then
        local h, s, v = rgb_to_hsv((A[1] or 0) / 255, (A[2] or 0) / 255, (A[3] or 0) / 255)
        -- a grey or dark base still shows a rainbow
        if s < 0.6 then s = 0.85 end
        if v < 0.45 then v = 0.85 end
        local r, g, b = hsv_to_rgb((h + phase) % 1, s, v)
        return { r * 255, g * 255, b * 255, A[4] or 255 }
    end
    -- pulse: smoothly there and back
    local B = a.b or A
    local k = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
    local out = {}
    for i = 1, 4 do
        local x, y = A[i] or 255, B[i] or (A[i] or 255)
        out[i] = x + (y - x) * k
    end
    return out
end

local function animate()
    local anims = state.payload and state.payload.anim
    if not anims or #anims == 0 or #state.targets == 0 then return end
    local t = state.frame / 60
    local colors = {}
    for i, a in ipairs(anims) do colors[i] = anim_color(a, t) end
    for _, tg in ipairs(state.targets) do
        if still_valid(tg.data, tg.data_type) and still_valid(tg.ctrl, tg.ctrl_type) then
            for i, a in ipairs(anims) do
                pcall(apply_path, tg.data, a.path, colors[i], true)
            end
            pcall(function() tg.ctrl:call("SetColor(System.Int32)", tg.num) end)
        end
    end
end

-- -------------------------------------------------------------------------

local function stop()
    restore()
    for _, ctrl in ipairs(controllers()) do
        pcall(function() ctrl:call("SetColor(System.Int32)", ctrl:get_field("ColorNum")) end)
    end
    state.payload = nil
    state.signature = ""
    state.status = "stopped — original colours restored"
end

local function dump()
    local out = { controllers = {} }
    for _, ctrl in ipairs(controllers()) do
        local data, num = current_data(ctrl)
        table.insert(out.controllers, {
            object = go_name(ctrl),
            side = side_of(ctrl),
            colorNum = num,
            clusters = data and cluster_names(data) or {},
        })
    end
    json.dump_file(DUMP_FILE, out)
    state.status = string.format("dumped %d colour controller(s) to %s", #out.controllers, DUMP_FILE)
end

re.on_frame(function()
    if not state.enabled then return end
    state.frame = state.frame + 1

    if state.payload and state.frame % state.anim_every == 0 then
        local ok, err = pcall(animate)
        if not ok then state.status = "animation error: " .. tostring(err) end
    end

    -- new fighters on screen (next round / match): apply the preview to them too
    if state.payload and state.frame % state.rescan_every == 0 then
        local ok, sig = pcall(function() return signature(controllers()) end)
        if ok and sig ~= state.signature then
            local aok, res = pcall(apply, state.payload)
            if not aok then state.status = "error: " .. tostring(res) end
        end
    end

    if state.frame % state.check_every ~= 0 then return end
    local ok, data = pcall(json.load_file, LIVE_FILE)
    if ok and data and data.stamp ~= state.last_stamp then
        state.last_stamp = data.stamp
        if data.stop then
            pcall(stop)
            report(data.stamp, 1)
        elseif data.dump then
            local dok, err = pcall(dump)
            if not dok then state.status = "error: " .. tostring(err) end
            report(data.stamp, 0)
        else
            state.payload = data
            state.anim_every = math.max(1, math.floor(tonumber(data.anim_every) or 2))
            local aok, res = pcall(apply, data)
            if not aok then state.status = "error: " .. tostring(res); res = 0 end
            report(data.stamp, res)
        end
    end
end)

re.on_draw_ui(function()
    if imgui.tree_node("SF6 Mod Editor - live preview") then
        local _
        _, state.enabled = imgui.checkbox("Enabled", state.enabled)
        imgui.text("Status: " .. state.status)
        if imgui.button("Re-apply") and state.payload then pcall(apply, state.payload) end
        imgui.same_line()
        if imgui.button("Stop preview") then pcall(stop) end
        imgui.same_line()
        if imgui.button("Dump colour controllers") then pcall(dump) end
        imgui.tree_pop()
    end
end)
