#!lua flags=allow-oom
-- Sample N keys of one prefix via SCAN MATCH, return MEMORY USAGE per sampled key.
local cursor = KEYS[1]
local match = ARGV[1]
local want = tonumber(ARGV[2])
local samples = {}
local iters = 0
while #samples < want and iters < 300 do
  local res = redis.call('SCAN', cursor, 'MATCH', match, 'COUNT', '400')
  cursor = res[1]
  for i = 1, #res[2] do
    local mu = redis.call('MEMORY', 'USAGE', res[2][i])
    if type(mu) == 'number' and mu > 0 then samples[#samples+1] = mu end
    if #samples >= want then break end
  end
  iters = iters + 1
  if cursor == '0' then break end
end
return {cursor, samples}
