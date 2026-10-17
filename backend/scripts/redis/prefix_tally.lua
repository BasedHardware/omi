#!lua flags=allow-oom
-- Time-bounded prefix tally. Client loops with cursor until '0'.
local cursor = KEYS[1]
local budget_ms = 3500
local start = redis.call('TIME')
local start_ms = start[1] * 1000 + start[2] / 1000
local buckets = {}
local order = {}
local total = 0
local iters = 0
local fat = {}   -- keys seen with very long names (proxy for big strings); capped
while true do
  local res = redis.call('SCAN', cursor, 'COUNT', '500')
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
    if not b then b = 0; buckets[pfx] = b; order[#order+1] = pfx end
    buckets[pfx] = b + 1
    if #k > 180 and #fat < 40 then fat[#fat+1] = k end
  end
  iters = iters + 1
  if cursor == '0' then break end
  local now = redis.call('TIME')
  local now_ms = now[1] * 1000 + now[2] / 1000
  if now_ms - start_ms > budget_ms or iters >= 3000 then break end
end
local out = {}
for _, pfx in ipairs(order) do out[#out+1] = {pfx, buckets[pfx]} end
return {total, cursor, iters, out, fat}
