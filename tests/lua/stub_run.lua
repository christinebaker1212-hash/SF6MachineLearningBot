-- MOCK harness for reframework/autorun/sf6bot_state.lua (NOT the game). Stubs the REFramework API
-- (sdk, re, json, imgui) and simulates what was measured on the user's PC (2026-10-02):
-- UpdateGameInfo runs once per RENDER; at fast replay speeds several game ticks pass per render.
-- Simulated methods for v7 discovery: "nBattle.sGame.UpdateTick" (once per game tick),
-- "nBattle.sGame.UpdateDraw" (once per render), "nBattle.cPlayer.MoveCalc" (very chatty).
-- usage: lua5.4 stub_run.lua <script> <outdir> <ticks_per_render> <renders> [per_tick=1|0] [pause_at]
--        [saved_choice=0|1] [fail_first=0|1]
-- fail_first=1: the best per-tick candidate (UpdateTick) runs in a context where player state can't
-- be read (as observed in game: the first chosen method wrote no lines); a second per-tick method
-- (nBattle.cPlayer.move_player) works. v8 must drop the first and confirm the second.
local script, outdir, tpr, renders = arg[1], arg[2], tonumber(arg[3]), tonumber(arg[4])
local per_tick_on = (arg[5] or "1") == "1"
local pause_at = tonumber(arg[6] or "-1")
local saved_choice = (arg[7] or "0") == "1"
local fail_first = (arg[8] or "0") == "1"
-- bar=1: a Training Mode frame-meter widget (v9 frame bar). Ring buffer of BAR_N cells; a move every
-- 16 ticks (10 busy ticks: P1 7 7 7 13 13 8 8 8 8 8, P2 hitstun 9 from the hit), then 6 idle ticks. A new
-- move after idle CLEARS the buffer and starts at cell 0 (model of the game, unverified); one long move
-- (super: 30 busy ticks) wraps the ring.
local bar_on = (arg[9] or "0") == "1"
local BAR_N = 20
local bar_cells = {}
for i = 0, BAR_N - 1 do bar_cells[i] = { 0, 0 } end
local bar_head, bar_t, sim_busy = -1, 0, false
local P1_MOVE = { 7, 7, 7, 13, 13, 8, 8, 8, 8, 8 }
local function bar_tick(t)
    -- ticks 1..160: ten short moves; ticks 161..200: one 30-tick move, then idle
    local pos, len
    if t <= 160 then pos, len = (t - 1) % 16 + 1, 10 else pos, len = t - 160, 30 end
    if pos > len then sim_busy = false; return end
    sim_busy = true
    if pos == 1 then for i = 0, BAR_N - 1 do bar_cells[i] = { 0, 0 } end; bar_head = -1 end
    bar_head = (bar_head + 1) % BAR_N
    local p1 = len == 10 and P1_MOVE[pos] or (pos <= 5 and 7 or pos <= 8 and 13 or 8)
    local p2 = pos >= 4 and 9 or 0
    bar_cells[bar_head] = { p1, p2 }
end
local function obj(fields, calls)
    return { get_field = function(_, n) return fields[n] end,
             call = function(_, n, ...) return calls[n](...) end }
end
local function cell_obj(side, i)
    return obj(setmetatable({}, { __index = function(_, n)
        if n == "FrameType" then return bar_cells[i][side] end
        if n == "Frame" then return i end
        return 0 end }), {})
end
local function list_obj(n, item) return obj({}, { get_Count = function() return n end, get_Item = item }) end
local fnd = { [0] = list_obj(BAR_N, function(i) return cell_obj(1, i) end),
              [1] = list_obj(BAR_N, function(i) return cell_obj(2, i) end) }
local meter = list_obj(2, function(i) return obj({ FrameNumDatas = fnd[i] }, {}) end)
local widget = obj({}, { get_SSData = function() return obj({ MeterDatas = meter }, {}) end })
local entry = obj({ key = 5, value = list_obj(1, function() return widget end) }, {})
local training = obj({ _ViewUIWigetDict = obj({ _entries = list_obj(1, function() return entry end) }, {}) }, {})
local in_failing = false
local timer = 0
local hooks = {}           -- method label -> post function
local on_frame = nil
local files = {}           -- json.dump_file / load_file store
if saved_choice then files["sf6bot_tickhook.json"] = { method = "nBattle.sGame.UpdateTick", confirmed = true } end

local function method(td_name, name) return { get_name = function() return name end, _label = td_name .. "." .. name } end
local function typedef(full, names)
    local ms = {}
    for _, n in ipairs(names) do ms[#ms + 1] = method(full, n) end
    return { get_full_name = function() return full end, get_methods = function() return ms end,
             get_method = function(_, n) for _, m in ipairs(ms) do if m.get_name() == n then return m end end end,
             get_field = function() return nil end }
end
local td_game = typedef("nBattle.sGame", per_tick_on and { "UpdateTick", "UpdateDraw", "GetTimer" } or { "UpdateDraw", "GetTimer" })
local td_player = typedef("nBattle.cPlayer", fail_first and { "MoveCalc", "IsDead", "move_player" } or { "MoveCalc", "IsDead" })
local td_med = typedef("app.FBattleMediator", { "UpdateGameInfo" })
local field = function(v) return { get_data = function() return v end } end
local player = setmetatable({ get_type_definition = function() return td_player end }, { __index = function(_, k)
    if k == "act_st" and bar_on then return sim_busy and 1 or 0 end
    return nil end })
local game = setmetatable({ get_type_definition = function() return td_game end }, {
    __index = function(_, k) if k == "stage_timer" then return timer end end })
local gBattle = {
    get_full_name = function() return "gBattle" end, get_methods = function() return {} end,
    get_field = function(_, name)
        if name == "Player" then
            if in_failing then error("player state not readable in this context (simulated)") end
            return field({ mcPlayer = { [0] = player, [1] = player } })
        end
        if name == "Team" then return field({ mcTeam = { [0] = {}, [1] = {} } }) end
        if name == "Game" then return field(game) end
        if name == "Round" then return field({ RoundNo = 0 }) end
        return field(nil)
    end,
}
local types = { gBattle = gBattle, ["app.FBattleMediator"] = td_med, ["nBattle.sGame"] = td_game,
                ["nBattle.cPlayer"] = td_player }
sdk = {
    find_type_definition = function(n) return types[n] end,
    hook = function(m, pre, post) hooks[m._label] = post end,
    get_managed_singleton = function(n)
        if bar_on and n == "app.training.TrainingManager" then return training end
        return nil
    end,
    to_managed_object = function() return nil end,
}
re = { on_frame = function(f) on_frame = f end, on_draw_ui = function() end, on_script_reset = function() end }
json = { dump_file = function(name, t) files[name] = t end, load_file = function(name) return files[name] end }
imgui = {}
local real_open = io.open
io.open = function(path, mode) return real_open(outdir .. "/" .. path, mode) end
dofile(script)
local function call(label, n) local f = hooks[label]; if f then for _ = 1, n do f(nil) end end end
for r = 1, renders do
    local paused = pause_at >= 0 and r > pause_at
    for _ = 1, tpr do
        if not paused then timer = timer + 1; if bar_on then bar_tick(timer) end end
        in_failing = fail_first
        call("nBattle.sGame.UpdateTick", 1)
        in_failing = false
        call("nBattle.cPlayer.move_player", 1)
    end
    if fail_first and r % 50 == 0 then call("nBattle.cPlayer.move_player", 1) end
    call("app.FBattleMediator.UpdateGameInfo", 1)
    call("nBattle.sGame.UpdateDraw", 1)
    call("nBattle.cPlayer.MoveCalc", 300)
    on_frame()
end
local saved = files["sf6bot_tickhook.json"]
print("FAILED=" .. tostring(saved and saved.failed_before and saved.failed_before[1] and saved.failed_before[1].method))
print("CHOSEN=" .. tostring(saved and saved.method))
