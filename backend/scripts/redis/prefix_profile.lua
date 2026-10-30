#!lua flags=allow-oom
-- Targeted prefix profiler: looped by client via KEYS[1]=cursor, ARGV[1]=match.
-- Returns {cursor, n, sum, max, ttl_buckets{lt1h,h1_6,h6_12,h12_24,gt24,negt}, avg_est}
local cursor = KEYS[1]
local match = ARGV[1]
local budget_ms = 2500
local t0 = redis.call('TIME')
local t0ms = t0[1] * 1000 + t0[2] / 1000
local n = 0
local sum = 0
local mx = 0
local b = {0, 0, 0, 0, 0, 0}  -- lt1h h1-6 h6-12 h12-24 gt24 nottl
local iters = 0
while true do
  local res = redis.call('SCAN', cursor, 'MATCH', match, 'COUNT', '400')
  cursor = res[1]
  for i = 1, #res[2] do
    local k = res[2][i]
    n = n + 1
    local ok, mu = pcall(function() return redis.call('MEMORY', 'USAGE', k) end)
    if ok and type(mu) == 'number' and mu > 0 then
      sum = sum + mu
      if mu > mx then mx = mu end
    end
    local ttl = redis.call('PTTL', k)
    if ttl == -1 then b[6] = b[6] + 1
    elseif ttl == -2 then -- expired between scan and pttl; ignore
    elseif ttl < 3600000 then b[1] = b[1] + 1
    elseif ttl < 21600000 then b[2] = b[2] + 1
    elseif ttl < 43200000 then b[3] = b[3] + 1
    elseif ttl < 86400000 then b[4] = b[4] + 1
    else b[5] = b[5] + 1 end
  end
  iters = iters + 1
  if cursor == '0' then break end
  local now = redis.call('TIME')
  if (now[1] * 1000 + now[2] / 1000) - t0ms > budget_ms or iters >= 4000 then break end
end
return {cursor, n, sum, mx, b[1], b[2], b[3], b[4], b[5], b[6]}
