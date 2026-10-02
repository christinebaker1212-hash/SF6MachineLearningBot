-- MOCK harness for reframework/autorun/sf6bot_state.lua (NOT the game): stubs the REFramework API
-- (sdk, re, json, imgui), drives the per-tick hook and the render callback, and prints the
-- written lines' (src, stage_timer) so tests/test_exporter_lua.py can check v6 behaviour.
-- usage: lua5.4 stub_run.lua <script> <outdir> <ticks_per_render> <renders> [hook=1|0] [pause_at]
local script, outdir, tpr, renders, hook_on, pause_at = arg[1], arg[2], tonumber(arg[3]), tonumber(arg[4]),
    (arg[5] or "1") == "1", tonumber(arg[6] or "-1")
local timer = 0
local hook_post = nil
local on_frame = nil
local field = function(v) return { get_data = function() return v end } end
local player = setmetatable({}, { __index = function() return nil end })
local gBattle = {
    get_field = function(_, name)
        if name == "Player" then return field({ mcPlayer = { [0] = player, [1] = player } }) end
        if name == "Team" then return field({ mcTeam = { [0] = {}, [1] = {} } }) end
        if name == "Game" then return field({ stage_timer = timer }) end
        if name == "Round" then return field({ RoundNo = 0 }) end
        return field(nil)
    end,
}
sdk = {
    find_type_definition = function(n)
        if n == "gBattle" then return gBattle end
        if n == "app.FBattleMediator" then return { get_method = function() return {} end } end
        return nil
    end,
    hook = function(_, pre, post) hook_post = post end,
    get_managed_singleton = function() return nil end,
    to_managed_object = function() return nil end,
}
re = { on_frame = function(f) on_frame = f end, on_draw_ui = function() end, on_script_reset = function() end }
json = { dump_file = function() end }
imgui = {}
local real_open = io.open
io.open = function(path, mode) return real_open(outdir .. "/" .. path, mode) end
dofile(script)
for r = 1, renders do
    local paused = pause_at >= 0 and r > pause_at
    for _ = 1, tpr do
        if not paused then timer = timer + 1 end
        if hook_on and hook_post then hook_post(nil) end
    end
    on_frame()
end
