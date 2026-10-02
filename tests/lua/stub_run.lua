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
local player = setmetatable({ get_type_definition = function() return td_player end }, { __index = function() return nil end })
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
    get_managed_singleton = function() return nil end,
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
        if not paused then timer = timer + 1 end
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
