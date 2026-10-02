-- sf6bot game-state exporter for REFramework (Street Fighter 6).
-- Writes one JSON line per GAME frame (stage_timer tick) to reframework/data/sf6bot_state.jsonl.
-- Sources ("src"): "tick" = a per-game-tick method found by v7 discovery (below), "ugi" =
-- app.FBattleMediator.UpdateGameInfo (measured 2026-10-02: once per RENDER, so it misses frames at
-- 8x), "frame" = the render callback (fallback + pause heartbeat). Lines are deduplicated on
-- (round, stage_timer), so each game frame is written once.
-- v7 DISCOVERY: when the game runs faster than it renders (fast replay), READ-ONLY counting hooks
-- on update-like methods of the battle objects we already read find the method that runs once
-- per game tick; it is then used to write lines and saved to reframework/data/sf6bot_tickhook.json
-- for the next start. The heartbeat file reports the candidates and the choice.
-- Read-only: it reads battle state and never changes the game.
-- Field names come from community scripts (rkaganda/SF6_replay_capture, haruno-ku/SF6_Tools);
-- every read is protected so a renamed field shows up in "missing" instead of crashing.
-- Offline, or in the Capcom-authorised ranked experiment only (see HANDOFF.md section 2).

-- io.open path rules differ between REFramework builds; try these in order and report which worked.
-- Verified on the user's REFramework (2026-10-01): io.open paths are relative to reframework/data,
-- so the plain name lands in <SF6>/reframework/data/sf6bot_state.jsonl. The others are fallbacks.
local CANDIDATE_PATHS = { "sf6bot_state.jsonl", "reframework/data/sf6bot_state.jsonl" }
local SCRIPT_VERSION = 7          -- must match sf6bot/game_state.py EXPECTED_SCRIPT_VERSION
local OUT_PATH = "(none)"
local INFO_EVERY = 60             -- heartbeat file (json.dump_file -> reframework/data) every N frames
local MAX_LINES = 200000          -- truncate the file after this many lines (~1 hour at 60 fps)
local IDLE_EVERY = 30             -- outside battle, write a heartbeat every N frames
local STILL_EVERY = 30            -- in battle with the clock stopped (pause), repeat a line every N renders

local enabled = true
local fh = nil
local lines = 0
local frame_no = 0
local last_error = ""
local last_missing = ""
local hook_calls, tick_lines, frame_lines = 0, 0, 0
local last_key = nil              -- "round:stage_timer" of the last battle line written
local renders_since_write = 0
local export_battle = nil         -- defined below; called from the hooks and from re.on_frame
local tick_report = nil           -- defined below (v7 discovery report for the heartbeat file)
local ugi_lines = 0

local open_errors = {}

local function open_file()
    if fh then pcall(function() fh:close() end) end
    fh = nil
    lines = 0
    open_errors = {}
    for _, path in ipairs(CANDIDATE_PATHS) do
        local ok, f, err = pcall(io.open, path, "w")
        if ok and f then
            fh = f
            OUT_PATH = path
            return
        end
        open_errors[#open_errors + 1] = path .. ": " .. tostring(ok and err or f)
    end
    last_error = "could not open any output file: " .. table.concat(open_errors, " | ")
end

local function write_info(in_battle)
    pcall(function()
        json.dump_file("sf6bot_exporter_info.json", {
            version = SCRIPT_VERSION, frame = frame_no, path = OUT_PATH, lines = lines, enabled = enabled,
            hook_calls = hook_calls, tick_lines = tick_lines, frame_lines = frame_lines,
            ugi_lines = ugi_lines, tick_hook = tick_report and tick_report() or nil,
            in_battle = in_battle, last_error = last_error, missing = last_missing,
            open_errors = table.concat(open_errors, " | "),
        })
    end)
end

local function try(f)
    local ok, v = pcall(f)
    if ok then return v end
    return nil
end

local function sfix(o)
    if o == nil then return nil end
    local ok, s = pcall(function() return o:call("ToString()") end)
    if ok and s then return tonumber(s) end
    return nil
end

local function enc(v)
    local t = type(v)
    if t == "number" then
        if v == math.floor(v) and math.abs(v) < 1e15 then return string.format("%d", v) end
        return string.format("%.5f", v)
    elseif t == "boolean" then return v and "true" or "false"
    elseif t == "string" then return '"' .. v:gsub('[%c"\\]', "") .. '"'
    end
    return "null"
end

-- Character ids (ESF numbers) via a READ-ONLY hook on app.FBattleMediator.UpdateGameInfo, the same
-- approach as haruno-ku/SF6_Tools SF6_DistanceViewer.lua. The hook only reads; it never changes args.
local chara = { [0] = nil, [1] = nil }
pcall(function()
    local t_med = sdk.find_type_definition("app.FBattleMediator")
    local method = t_med and t_med:get_method("UpdateGameInfo")
    if not method then return end
    sdk.hook(method, function(args)
        pcall(function()
            local obj = sdk.to_managed_object(args[2])
            local arr = obj and t_med:get_field("PlayerType"):get_data(obj)
            if arr and arr:call("get_Length") >= 2 then
                for i = 0, 1 do
                    local e = arr:call("GetValue", i)
                    if e then chara[i] = e:get_type_definition():get_field("value__"):get_data(e) end
                end
            end
        end)
    end, function(retval)
        hook_calls = hook_calls + 1
        if enabled and export_battle then
            local ok, err = pcall(export_battle, "ugi")
            if not ok then last_error = "ugi: " .. tostring(err) end
        end
        return retval
    end)
end)

-- ---- v7: per-game-tick method discovery (READ-ONLY counting hooks) ----------------------------
local TICK_FILE = "sf6bot_tickhook.json"
local DISCOVER_RENDERS = 600      -- evaluate after this many in-battle renders...
local FAST_RATIO = 1.5            -- ...if the clock advanced at least this much faster than renders
local MAX_CANDIDATES = 40
local MAX_CALLS_PER_RENDER = 200  -- stop counting methods called more often than this (cost)
local NAME_HINTS = { "update", "step", "tick", "exec", "proc", "frame", "move" }
local tick = { chosen = nil, candidates = {}, started = false, done = false, renders = 0, advance = 0,
               last_timer = nil, result = "not started", writes = 0 }

local function battle_timer()
    local gb = sdk.find_type_definition("gBattle")
    return gb and try(function() return gb:get_field("Game"):get_data(nil).stage_timer end)
end

local function hook_counter(td, m, label)
    local c = { name = label, calls = 0, changes = 0, last = nil, off = false }
    local ok = pcall(sdk.hook, m, function(args) end, function(retval)
        if tick.chosen == label then
            if enabled and export_battle then
                tick.writes = tick.writes + 1
                local okx, err = pcall(export_battle, "tick")
                if not okx then last_error = "tick: " .. tostring(err) end
            end
        elseif not tick.done and not c.off then
            c.calls = c.calls + 1
            local t = battle_timer()
            if t ~= c.last then c.changes = c.changes + 1; c.last = t end
        end
        return retval
    end)
    if ok then tick.candidates[#tick.candidates + 1] = c end
    return ok
end

local function method_label(td, m)
    local tn = try(function() return td:get_full_name() end) or "?"
    local mn = try(function() return m:get_name() end) or "?"
    return tn .. "." .. mn
end

local function load_chosen()
    local saved = try(function() return json.load_file(TICK_FILE) end)
    if type(saved) ~= "table" or type(saved.method) ~= "string" then return false end
    local tn, mn = saved.method:match("^(.*)%.([^%.]+)$")
    local td = tn and sdk.find_type_definition(tn)
    local m = td and try(function() return td:get_method(mn) end)
    if not m then tick.result = "saved method not found: " .. saved.method; return false end
    if hook_counter(td, m, saved.method) then
        tick.chosen, tick.done, tick.result = saved.method, true, "loaded " .. TICK_FILE
        return true
    end
    return false
end

local function start_discovery(p1)
    tick.started = true
    if load_chosen() then return end
    local seen, tds = {}, {}
    local function add(td)
        local n = td and try(function() return td:get_full_name() end)
        if n and not seen[n] then seen[n] = true; tds[#tds + 1] = td end
    end
    local gb = sdk.find_type_definition("gBattle")
    add(sdk.find_type_definition("app.FBattleMediator"))
    add(gb)
    for _, f in ipairs({ "Game", "Round", "Player", "Team" }) do
        local o = gb and try(function() return gb:get_field(f):get_data(nil) end)
        add(o and try(function() return o:get_type_definition() end))
    end
    add(p1 and try(function() return p1:get_type_definition() end))
    for _, td in ipairs(tds) do
        local methods = try(function() return td:get_methods() end) or {}
        for _, m in ipairs(methods) do
            if #tick.candidates >= MAX_CANDIDATES then break end
            local mn = (try(function() return m:get_name() end) or ""):lower()
            if mn ~= "updategameinfo" then
                for _, h in ipairs(NAME_HINTS) do
                    if mn:find(h, 1, true) then hook_counter(td, m, method_label(td, m)); break end
                end
            end
        end
    end
    tick.result = "discovering (" .. #tick.candidates .. " candidates); play a replay at 8x"
end

-- A per-tick method found earlier is hooked at script start, so no frame is missed.
if pcall(load_chosen) and tick.chosen then tick.started = true end

-- once per render while in battle
local function discovery_step()
    if tick.done then return end
    local t = battle_timer()
    if type(t) == "number" and type(tick.last_timer) == "number" and t > tick.last_timer then
        tick.advance = tick.advance + (t - tick.last_timer)
    end
    tick.last_timer = t
    tick.renders = tick.renders + 1
    for _, c in ipairs(tick.candidates) do
        if c.calls > MAX_CALLS_PER_RENDER * tick.renders then c.off = true end
    end
    if tick.renders < DISCOVER_RENDERS then return end
    if tick.advance < FAST_RATIO * tick.renders then
        -- not running fast (1x play): per-render and per-tick methods look the same; keep waiting
        tick.renders, tick.advance = 0, 0
        for _, c in ipairs(tick.candidates) do c.calls, c.changes = 0, 0 end
        tick.result = "waiting for a fast replay (8x) to tell per-tick from per-render methods"
        return
    end
    local best = nil
    for _, c in ipairs(tick.candidates) do
        if not c.off and c.changes >= 0.95 * tick.advance and c.calls <= 4 * tick.advance then
            if best == nil or math.abs(c.calls - tick.advance) < math.abs(best.calls - tick.advance) then
                best = c
            end
        end
    end
    tick.done = true
    if best then
        tick.chosen = best.name
        tick.result = "chosen " .. best.name
        pcall(json.dump_file, TICK_FILE, { method = best.name, calls = best.calls, changes = best.changes,
                                           advance = tick.advance, renders = tick.renders })
    else
        tick.result = "no per-tick method among " .. #tick.candidates .. " candidates"
    end
end

tick_report = function()
    local top = {}
    for _, c in ipairs(tick.candidates) do top[#top + 1] = c end
    table.sort(top, function(a, b) return a.changes > b.changes end)
    local out = {}
    for i = 1, math.min(8, #top) do
        out[i] = { name = top[i].name, calls = top[i].calls, changes = top[i].changes, off = top[i].off }
    end
    return { chosen = tick.chosen, result = tick.result, renders = tick.renders, advance = tick.advance,
             writes = tick.writes, candidates = #tick.candidates, top = out }
end

-- Training Mode frame meter (the game's own Startup / Total / Advantage). READ only. Field names are
-- not documented, so every scalar field of both players' MeterDatas items is exported (discovery);
-- sf6bot maps the meaningful ones after comparing with the on-screen numbers.
-- Path from haruno-ku/SF6_Tools: TrainingManager._tCommon.SnapShotDatas[0]._DisplayData.FrameMeterSSData.
local fm_fields_cache = nil
local fm_last, fm_last_frame = "", -1000

local function scalar_text(v)
    local tv = type(v)
    if tv == "number" or tv == "boolean" then return v end
    if tv == "string" then return v end
    if tv == "userdata" or tv == "table" then
        local ok, s = pcall(function() return v:call("ToString()") end)
        if ok and type(s) == "string" then return s end
        local ok2, s2 = pcall(tostring, v)   -- some REFramework strings stringify directly
        if ok2 and type(s2) == "string" and not s2:find("^sol%.") and not s2:find("^table:") then return s2 end
    end
    return nil
end

local function read_frame_meter()
    local tm = sdk.get_managed_singleton("app.training.TrainingManager")
    if not tm then return nil end
    local md = tm._tCommon.SnapShotDatas[0]._DisplayData.FrameMeterSSData.MeterDatas
    local parts = {}
    for i = 0, 1 do
        local item = md:call("get_Item", i)
        if not item then return nil end
        if not fm_fields_cache then
            fm_fields_cache = {}
            for _, f in ipairs(item:get_type_definition():get_fields()) do
                local n = f:get_name()
                if not f:is_static() and not n:find("Datas") then fm_fields_cache[#fm_fields_cache + 1] = f end
            end
        end
        local kv = {}
        for _, f in ipairs(fm_fields_cache) do
            local ok, v = pcall(function() return f:get_data(item) end)
            if ok then
                local x = scalar_text(v)
                if x ~= nil then kv[#kv + 1] = '"' .. f:get_name() .. '":' .. (type(x) == "string" and
                    ('"' .. x:gsub('[%c"\\]', "") .. '"') or (type(x) == "boolean" and (x and "true" or "false")
                    or (x == math.floor(x) and string.format("%d", x) or string.format("%.4f", x)))) end
            end
        end
        parts[#parts + 1] = '"' .. (i == 0 and "p1" or "p2") .. '":{' .. table.concat(kv, ",") .. "}"
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local PFIELDS = { "chara", "input", "input_sw", "hp", "hp_max", "hp_recoverable", "drive", "drive_wait", "super", "x", "y",
                  "facing_right", "dir_bit", "action_id", "action_frame", "action_frames_total", "hitstop",
                  "hitstun", "blockstun", "pose", "act_st", "invuln" }

local function read_player(p, t, idx)
    local r = {}
    r.chara = chara[idx]
    -- Raw per-frame input masks (READ only). Bit meanings are measured by `sf6bot input-map`.
    r.input = try(function() return p.pl_input_new end)
    r.input_sw = try(function() return p.pl_sw_new end)
    r.hp = try(function() return p.vital_new end)
    r.hp_max = try(function() return p.vital_max end)
    r.hp_recoverable = try(function() return p.heal_new end)
    r.drive = try(function() return p.focus_new end)
    r.drive_wait = try(function() return p.focus_wait end)
    r.super = try(function() return t.mSuperGauge end)
    r.x = try(function() return p.pos.x.v / 6553600.0 end)
    r.y = try(function() return p.pos.y.v / 6553600.0 end)
    -- BitValue bit 128: observed on the user's game (2026-10-01) set for the player on the LEFT
    -- (x=-1.5) and clear for the player on the right, i.e. set = facing RIGHT. (A community
    -- comment claims the opposite; state-check verifies this every run.)
    r.dir_bit = try(function() return math.floor(p.BitValue / 128) % 2 end)
    r.facing_right = try(function() return r.dir_bit == 1 end)
    if r.dir_bit == nil then r.facing_right = nil end
    local eng = try(function() return p.mpActParam.ActionPart._Engine end)
    r.action_id = try(function() return eng:get_ActionID() end)
    r.action_frame = try(function() return sfix(eng:get_ActionFrame()) end)
    r.action_frames_total = try(function() return sfix(eng:get_ActionFrameNum()) end)
    r.hitstop = try(function() return p.hit_stop end)
    r.hitstun = try(function() return p.damage_time end)
    r.blockstun = try(function() return p.guard_time end)
    r.pose = try(function() return p.pose_st end)
    r.act_st = try(function() return p.act_st end)
    r.invuln = try(function() return p.muteki_time end)
    return r
end

local function encode_player(r, prefix, missing)
    local parts = {}
    for _, k in ipairs(PFIELDS) do
        local v = r[k]
        if v == nil and k ~= "chara" then missing[#missing + 1] = prefix .. "." .. k end  -- chara: known after match start
        local tv = type(v)
        if tv ~= "number" and tv ~= "boolean" and tv ~= "nil" then v = tonumber(tostring(v)) end
        parts[#parts + 1] = '"' .. k .. '":' .. enc(v)
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local function write_line(s)
    if not fh then open_file() end
    if not fh then return end
    fh:write(s, "\n")
    fh:flush()
    lines = lines + 1
    if lines >= MAX_LINES then open_file() end
end

-- One battle line. src = "tick" (UpdateGameInfo hook) or "frame" (render callback).
-- Returns false if not in battle. Dedupes on (round, stage_timer) so each game frame is written once.
export_battle = function(src)
    local gb = sdk.find_type_definition("gBattle")
    local players = gb and try(function() return gb:get_field("Player"):get_data(nil).mcPlayer end)
    local teams = gb and try(function() return gb:get_field("Team"):get_data(nil).mcTeam end)
    local p1 = players and try(function() return players[0] end)
    local p2 = players and try(function() return players[1] end)
    if not (p1 ~= nil and p2 ~= nil and teams ~= nil) then return false end
    local stage_timer = try(function() return gb:get_field("Game"):get_data(nil).stage_timer end)
    local round_no = try(function() return gb:get_field("Round"):get_data(nil).RoundNo end)
    local key = tostring(round_no) .. ":" .. tostring(stage_timer)
    if stage_timer ~= nil and key == last_key then
        -- this game frame is already written; the render path repeats it only as a pause heartbeat
        if src == "tick" or renders_since_write < STILL_EVERY then return true end
    end
    local missing = {}
    local r1 = read_player(p1, teams[0], 0)
    local r2 = read_player(p2, teams[1], 1)
    -- During loading/intros the player objects exist but are zeroed: not usable state.
    local ready = (r1.hp_max or 0) > 0 and (r2.hp_max or 0) > 0 and r1.action_id ~= nil and r2.action_id ~= nil
    local s1 = encode_player(r1, "p1", missing)
    local s2 = encode_player(r2, "p2", missing)
    if stage_timer == nil then missing[#missing + 1] = "stage_timer" end
    if round_no == nil then missing[#missing + 1] = "round" end
    local m = {}
    for i, k in ipairs(missing) do m[i] = '"' .. k .. '"' end
    local fm_part = ""
    local okfm, fm = pcall(read_frame_meter)
    if okfm and fm then
        if fm ~= fm_last or frame_no - fm_last_frame >= 60 then
            fm_part = ',"fm":' .. fm
            fm_last, fm_last_frame = fm, frame_no
        end
    end
    last_missing = table.concat(missing, ", ")
    write_line('{"v":' .. SCRIPT_VERSION .. ',"f":' .. frame_no .. ',"src":"' .. src .. '","in_battle":true,"ready":' ..
               enc(ready) .. ',"stage_timer":' .. enc(stage_timer) ..
               ',"round":' .. enc(round_no) .. fm_part .. ',"p1":' .. s1 .. ',"p2":' .. s2 ..
               ',"missing":[' .. table.concat(m, ",") .. ']}')
    last_key = key
    renders_since_write = 0
    if src == "tick" then tick_lines = tick_lines + 1
    elseif src == "ugi" then ugi_lines = ugi_lines + 1
    else frame_lines = frame_lines + 1 end
    return true
end

re.on_frame(function()
    if not enabled then return end
    frame_no = frame_no + 1
    renders_since_write = renders_since_write + 1
    local ok, err = pcall(function()
        local in_battle = export_battle("frame")
        if in_battle then
            if not tick.started then
                local gb = sdk.find_type_definition("gBattle")
                local pl = gb and try(function() return gb:get_field("Player"):get_data(nil).mcPlayer end)
                start_discovery(pl and try(function() return pl[0] end))
            end
            discovery_step()
        end
        if frame_no % INFO_EVERY == 1 then write_info(in_battle) end
        if not in_battle and frame_no % IDLE_EVERY == 0 then
            write_line('{"v":' .. SCRIPT_VERSION .. ',"f":' .. frame_no .. ',"in_battle":false,"ready":false}')
        end
    end)
    if not ok then last_error = tostring(err) end
end)

re.on_draw_ui(function()
    if imgui.tree_node("sf6bot state exporter") then
        local changed, v = imgui.checkbox("Export enabled", enabled)
        if changed then enabled = v end
        imgui.text("Script version " .. SCRIPT_VERSION .. ". Lines written: " .. tostring(lines) .. "  file: " .. OUT_PATH)
        imgui.text("Lines from per-tick hook: " .. tick_lines .. ", UpdateGameInfo: " .. ugi_lines ..
                   ", render: " .. frame_lines)
        imgui.text("Per-tick discovery: " .. tick.result)
        if last_missing ~= "" then imgui.text("Missing fields: " .. last_missing) end
        if last_error ~= "" then imgui.text("Last error: " .. last_error) end
        imgui.tree_pop()
    end
end)

re.on_script_reset(function()
    if fh then pcall(function() fh:close() end) end
    fh = nil
end)
