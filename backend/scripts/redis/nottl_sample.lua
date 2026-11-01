#!lua flags=allow-oom
-- Sample per prefix: no-TTL share + short key-shape samples (masked by client).
local cursor = KEYS[1]
local budget_ms = 2500
local t0 = redis.call('TIME')
local t0ms = t0[1] * 1000 + t0[2] / 1000
local buckets = {}   -- pfx -> {n, nottl}
local order = {}
local shapes = {}    -- pfx -> {sample key lengths + segment count}, plus 2 sample keys per prefix for client masking
local total = 0
local iters = 0
while true do
  local res = redis.call('SCAN', cursor, 'COUNT', '300')
  cursor = res[1]
  for i = 1, #res[2] do
    local k = res[2][i]
    total = total + 1
    local p1, p2 = string.match(k, '^([^:]+):([^:]+):')
    local pfx
    if p1 and p2 and #p2 <= 5 and string.match(p2, '^v%d') then
      pfx = p1 .. ':' .. p2
    else
      pfx = string.match(k, '^([^:]+)') or k
    end
    local b = buckets[pfx]
    if not b then b = {0, 0}; buckets[pfx] = b; order[#order+1] = pfx end
    b[1] = b[1] + 1
    if redis.call('PTTL', k) == -1 then b[2] = b[2] + 1 end
    local s = shapes[pfx]
    if not s then s = {0, 0, 0}; shapes[pfx] = s end
    if s[1] < 3 then
      s[1] = s[1] + 1
      s[#s+1] = k
    end
  end
  iters = iters + 1
  if cursor == '0' then break end
  local now = redis.call('TIME')
  if (now[1] * 1000 + now[2] / 1000) - t0ms > budget_ms or iters >= 2500 then break end
end
local out = {}
for _, pfx in ipairs(order) do
  local b = buckets[pfx]
  local s = shapes[pfx] or {0}
  out[#out+1] = {pfx, b[1], b[2], s[1], s[2] or '', s[3] or '', s[4] or ''}
end
return {total, cursor, out}
