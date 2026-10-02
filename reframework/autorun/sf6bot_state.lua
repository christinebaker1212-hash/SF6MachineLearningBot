-- sf6bot game-state exporter for REFramework (Street Fighter 6).
-- Writes one JSON line per GAME frame (stage_timer tick) to reframework/data/sf6bot_state.jsonl.
-- v6: lines are written from a hook on app.FBattleMediator.UpdateGameInfo ("src":"tick") when that
-- runs once per game tick, so fast replays (8x) no longer skip frames; the per-render callback
-- ("src":"frame") writes only when stage_timer moved without a tick line, plus a heartbeat every
-- 30 renders when the clock is stopped (pause). Whether UpdateGameInfo is per tick is UNVERIFIED:
-- the counters in the heartbeat file (hook_calls, tick_lines, frame_lines) show it.
-- Read-only: it reads battle state and never changes the game.
-- Field names come from community scripts (rkaganda/SF6_replay_capture, haruno-ku/SF6_Tools);
-- every read is protected so a renamed field shows up in "missing" instead of crashing.
-- Use OFFLINE only (Training Mode / CPU). Disable REFramework before playing online.

-- io.open path rules differ between REFramework builds; try these in order and report which worked.
-- Verified on the user's REFramework (2026-10-01): io.open paths are relative to reframework/data,
-- so the plain name lands in <SF6>/reframework/data/sf6bot_state.jsonl. The others are fallbacks.
local CANDIDATE_PATHS = { "sf6bot_state.jsonl", "reframework/data/sf6bot_state.jsonl" }
local SCRIPT_VERSION = 6          -- must match sf6bot/game_state.py EXPECTED_SCRIPT_VERSION
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
local export_battle = nil         -- defined below; called from the hook and from re.on_frame

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
            local ok, err = pcall(export_battle, "tick")
            if not ok then last_error = "tick: " .. tostring(err) end
        end
        return retval
    end)
end)

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
    if src == "tick" then tick_lines = tick_lines + 1 else frame_lines = frame_lines + 1 end
    return true
end

re.on_frame(function()
    if not enabled then return end
    frame_no = frame_no + 1
    renders_since_write = renders_since_write + 1
    local ok, err = pcall(function()
        local in_battle = export_battle("frame")
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
        imgui.text("Game-tick hook calls: " .. hook_calls .. ", lines from hook: " .. tick_lines ..
                   ", from render: " .. frame_lines)
        if last_missing ~= "" then imgui.text("Missing fields: " .. last_missing) end
        if last_error ~= "" then imgui.text("Last error: " .. last_error) end
        imgui.tree_pop()
    end
end)

re.on_script_reset(function()
    if fh then pcall(function() fh:close() end) end
    fh = nil
end)
