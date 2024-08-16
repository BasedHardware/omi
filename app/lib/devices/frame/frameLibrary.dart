const String friendMicRecordAndSend = '''
function friendMicRecordAndSend(sample_rate, bit_depth)
    frame.microphone.stop()
    frame.microphone.start{sample_rate=sample_rate, bit_depth=bit_depth}
    local max_packet_size = frame.bluetooth.max_length() - 5
    local chunk_count = 0

    if max_packet_size % 2 ~= 0 then
        max_packet_size = max_packet_size - 1
    end

    while true do
        s = frame.microphone.read(320)
        if s == nil then
            break
        end
        if s ~= '' then
            local chunk_count_byte1 = chunk_count % 256
            local chunk_count_byte2 = math.floor(chunk_count / 256)

            if max_packet_size > 320 then
              while true do
                if pcall(frame.bluetooth.send, '\\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. '\\x00' .. s) then
                  break
                end 
              end
            else
              local partial_index = 0
              local partial_chunk = string.sub(s, 1, max_packet_size)
              while true do
                while true do
                  if pcall(frame.bluetooth.send, '\\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. string.char(partial_index) .. partial_chunk) then
                    break
                  end
                end
                partial_index = partial_index + 1
                s = string.sub(s, max_packet_size + 1)
                if s == '' then
                  break
                end
              end
            end
            chunk_count = chunk_count + 1
            if chunk_count > 65535 then
              chunk_count = 0
            end
        end
    end
    frame.microphone.stop()
end
''';
