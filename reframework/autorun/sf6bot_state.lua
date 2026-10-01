-- sf6bot game-state exporter for REFramework (Street Fighter 6).
-- Writes one JSON line per rendered frame to reframework/data/sf6bot_state.jsonl.
-- Read-only: it reads battle state and never changes the game.
-- Field names come from community scripts (rkaganda/SF6_replay_capture, haruno-ku/SF6_Tools);
-- every read is protected so a renamed field shows up in "missing" instead of crashing.
-- Use OFFLINE only (Training Mode / CPU). Disable REFramework before playing online.

-- io.open path rules differ between REFramework builds; try these in order and report which worked.
local CANDIDATE_PATHS = { "reframework/data/sf6bot_state.jsonl", "reframework\\data\\sf6bot_state.jsonl",
                          "sf6bot_state.jsonl" }
local OUT_PATH = "(none)"
local INFO_EVERY = 60             -- heartbeat file (json.dump_file -> reframework/data) every N frames
local MAX_LINES = 200000          -- truncate the file after this many lines (~1 hour at 60 fps)
local IDLE_EVERY = 30             -- outside battle, write a heartbeat every N frames

local enabled = true
local fh = nil
local lines = 0
local frame_no = 0
local last_error = ""
local last_missing = ""

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
            version = 2, frame = frame_no, path = OUT_PATH, lines = lines, enabled = enabled,
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

local PFIELDS = { "hp", "hp_max", "hp_recoverable", "drive", "drive_wait", "super", "x", "y",
                  "facing_left", "action_id", "action_frame", "action_frames_total", "hitstop",
                  "hitstun", "blockstun", "pose", "act_st", "invuln" }

local function read_player(p, t)
    local r = {}
    r.hp = try(function() return p.vital_new end)
    r.hp_max = try(function() return p.vital_max end)
    r.hp_recoverable = try(function() return p.heal_new end)
    r.drive = try(function() return p.focus_new end)
    r.drive_wait = try(function() return p.focus_wait end)
    r.super = try(function() return t.mSuperGauge end)
    r.x = try(function() return p.pos.x.v / 6553600.0 end)
    r.y = try(function() return p.pos.y.v / 6553600.0 end)
    r.facing_left = try(function() return math.floor(p.BitValue / 128) % 2 == 1 end)
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
        if v == nil then missing[#missing + 1] = prefix .. "." .. k end
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

re.on_frame(function()
    if not enabled then return end
    frame_no = frame_no + 1
    local ok, err = pcall(function()
        local gb = sdk.find_type_definition("gBattle")
        local players = gb and try(function() return gb:get_field("Player"):get_data(nil).mcPlayer end)
        local teams = gb and try(function() return gb:get_field("Team"):get_data(nil).mcTeam end)
        local p1 = players and try(function() return players[0] end)
        local p2 = players and try(function() return players[1] end)
        local in_battle = p1 ~= nil and p2 ~= nil and teams ~= nil
        if frame_no % INFO_EVERY == 1 then write_info(in_battle) end
        if not in_battle then
            if frame_no % IDLE_EVERY == 0 then
                write_line('{"v":1,"f":' .. frame_no .. ',"in_battle":false}')
            end
            return
        end
        local stage_timer = try(function() return gb:get_field("Game"):get_data(nil).stage_timer end)
        local round_no = try(function() return gb:get_field("Round"):get_data(nil).RoundNo end)
        local missing = {}
        local s1 = encode_player(read_player(p1, teams[0]), "p1", missing)
        local s2 = encode_player(read_player(p2, teams[1]), "p2", missing)
        if stage_timer == nil then missing[#missing + 1] = "stage_timer" end
        if round_no == nil then missing[#missing + 1] = "round" end
        local m = {}
        for i, k in ipairs(missing) do m[i] = '"' .. k .. '"' end
        last_missing = table.concat(missing, ", ")
        write_line('{"v":1,"f":' .. frame_no .. ',"in_battle":true,"stage_timer":' .. enc(stage_timer) ..
                   ',"round":' .. enc(round_no) .. ',"p1":' .. s1 .. ',"p2":' .. s2 ..
                   ',"missing":[' .. table.concat(m, ",") .. ']}')
    end)
    if not ok then last_error = tostring(err) end
end)

re.on_draw_ui(function()
    if imgui.tree_node("sf6bot state exporter") then
        local changed, v = imgui.checkbox("Export enabled", enabled)
        if changed then enabled = v end
        imgui.text("Lines written: " .. tostring(lines) .. "  file: " .. OUT_PATH)
        if last_missing ~= "" then imgui.text("Missing fields: " .. last_missing) end
        if last_error ~= "" then imgui.text("Last error: " .. last_error) end
        imgui.tree_pop()
    end
end)

re.on_script_reset(function()
    if fh then pcall(function() fh:close() end) end
    fh = nil
end)
