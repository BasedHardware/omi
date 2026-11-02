#!lua flags=allow-oom
-- Time-budgeted deep sample: per-prefix {n,sum,max} + global top biggest keys.
local cursor = KEYS[1]
local budget_ms = 3500
local t0 = redis.call('TIME')
local t0ms = t0[1] * 1000 + t0[2] / 1000
local buckets = {}   -- pfx -> {n, sum, max}
local order = {}
local big = {}       -- top list of {mu, key} kept sorted desc, cap 25
local total = 0
local iters = 0
while true do
  local res = redis.call('SCAN', cursor, 'COUNT', '300')
  cursor = res[1]
  local keys = res[2]
  for i = 1, #keys do
    local k = keys[i]
    total = total + 1
    local p1, p2 = string.match(k, '^([^:]+):([^:]+):')
    local pfx
    if p1 and p2 and #p2 <= 5 and string.match(p2, '^v%d') then
      pfx = p1 .. ':' .. p2
    else
      pfx = string.match(k, '^([^:]+)') or k
    end
    local b = buckets[pfx]
    if not b then b = {0, 0, 0}; buckets[pfx] = b; order[#order+1] = pfx end
    b[1] = b[1] + 1
    local ok, mu = pcall(function() return redis.call('MEMORY', 'USAGE', k) end)
    if ok and type(mu) == 'number' and mu > 0 then
      b[2] = b[2] + mu
      if mu > b[3] then b[3] = mu end
      -- insert into top list if bigger than the smallest tracked
      if #big < 25 then
        big[#big+1] = {mu, k}
      else
        local minidx = 1
        for j = 2, #big do if big[j][1] < big[minidx][1] then minidx = j end end
        if mu > big[minidx][1] then big[minidx] = {mu, k} end
      end
    end
  end
  iters = iters + 1
  if cursor == '0' then break end
  local now = redis.call('TIME')
  local nowms = now[1] * 1000 + now[2] / 1000
  if nowms - t0ms > budget_ms or iters >= 2500 then break end
end
-- sort big desc
table.sort(big, function(a, b2) return a[1] > b2[1] end)
local out = {}
for _, pfx in ipairs(order) do
  local b = buckets[pfx]
  out[#out+1] = {pfx, b[1], b[2], b[3]}
end
local bigout = {}
for i = 1, #big do bigout[#bigout+1] = {big[i][1], big[i][2]} end
return {total, cursor, iters, out, bigout}
