function receiveBluetoothData(data)
	if data ~= nil then
		local eqIdx = string.find(data, "=")
		if data == "CAMERA START" then
			queuedCameraData = nil
			if cameraState == 0 then
				--frame.camera.wake()
				cameraStateTime = frame.time.utc()
				cameraState = 9
			end
		elseif data == "CAMERA STOP" then
			if cameraState > 0 then
				--frame.camera.sleep()
			end
			cameraState = 0
		elseif data == "MIC START" then
			micData = nil
			if micState == 0 or micState == 2 then
				micState = 3
			end
		elseif data == "MIC STOP" then
			if micState > 2 then
				frame.microphone.stop()
			end
			micState = 0
		elseif data == "LOOP STOP" then
			if loopStatus > 0 then
				frame.microphone.stop()
			end
			if cameraState > 0 then
				--frame.camera.sleep()
			end
			loopStatus = 0
		elseif data == "HEARTBEAT" then
			heartbeat = frame.time.utc()
			if localHeartbeat < frame.time.utc() - 5 then
				print("FrameLib mainLoop() heartbeat timed out.  loopStatus = " .. loopStatus .. ", micState = " ..
						  micState .. ", cameraState = " .. cameraState)
				mainLoop()
			end
		elseif data == "GET loopStatus" then
			print("FrameLib loopStatus = " .. loopStatus)
			frame.bluetooth.send('\xE1' .. loopStatus)
		elseif data == "GET micState" then
			frame.bluetooth.send('\xE2' .. micState)
		elseif data == "GET cameraState" then
			frame.bluetooth.send('\xE3' .. cameraState)
		elseif data == "GET frameLibHash" then
			if frameLibHash ~= nil then
				frame.bluetooth.send('\xE4' .. frameLibHash)
			else
				frame.bluetooth.send('\xE4')
			end
		elseif eqIdx ~= nil then
			local key = string.sub(data, 1, eqIdx - 1)
			local value = string.sub(data, eqIdx + 1)
			if key=="timeUtc" then
				local _time = tonumber(value)
				if _time and _time >= 0 then
					frame.time.utc(value)
				end
			elseif key == "timeZone" then
				frame.time.zone(value)
			elseif key == "autoExpTimeDelay" then
				local _autoExpTimeDelay = tonumber(value)
				if _autoExpTimeDelay and _autoExpTimeDelay >= 0 and _autoExpTimeDelay <= 10 then
					autoExpTimeDelay = _autoExpTimeDelay
				end
			elseif key == "delayBetweenPhotos" then
				local _delayBetweenPhotos = tonumber(value)
				if _delayBetweenPhotos and _delayBetweenPhotos >= 0 then
					delayBetweenPhotos = _delayBetweenPhotos
				end
			elseif key == "sampleRate" then
				local _sampleRate = tonumber(value)
				if _sampleRate and _sampleRate >= 0 and _sampleRate <= 48000 then
					sampleRate = _sampleRate
				end
			elseif key == "bitDepth" then
				local _bitDepth = tonumber(value)
				if _bitDepth and (_bitDepth == 8 or _bitDepth == 16) then
					bitDepth = _bitDepth
				end
			end
		else
			print("didn't match anything! " .. data)
		end
		print("ECHO:" .. data)
	else
		print("data is nil")
	end
end
function padNumber(num, len)
	local str = tostring(num)
	while #str < len do
		str = '0' .. str
	end
	return str
end
function mainLoop()
	heartbeat = 0
	if photoQuality == nil then
		photoQuality = 25
	end
	if autoExpTimeDelay == nil then
		autoExpTimeDelay = 5
	end
	if delayBetweenPhotos == nil then
		delayBetweenPhotos = 15
	end
	if sampleRate == nil then
		sampleRate = 8000
	end
	if bitDepth == nil then
		bitDepth = 16
	end
	local lastAutoExpTime = 0
	-- cameraState: 0 = stopped, 1 = running, 2 = paused, 3 = exposing, 4 = capture, 5 = wait, 6 = send, 7 = done, 8 = waiting for next photo, 9 = waking up
	if cameraState == nil then
		cameraState = 0
	end
	-- micState: 0 = stopped, 1 = n/a, 2 = paused, 3 = starting, 4 = sending
	if micState == nil then
		micState = 0
	end
	cameraStateTime = frame.time.utc()
	local photoChunkIndex = 0
	local audioChunkIndex = 0
	local showStatus = true
	micData = nil
	--loopStatus: 0 = stopped, 1 = running, 2 = paused
	loopStatus = 1
	local micLoops = 0
	local prevStatus = 0
	lastStatusUpdate = 0
	queuedCameraData = nil
	local queuedMicData = nil
	local maxDataLen = frame.bluetooth.max_length() - 50
	if maxDataLen % 2 ~= 0 then
		maxDataLen = maxDataLen - 1
	end
	while loopStatus == 1 do
		localHeartbeat = frame.time.utc()
		if lastStatusUpdate < frame.time.utc() - 1 then
			lastStatusUpdate = frame.time.utc()
			local battery = frame.battery_level()
			--status: 0=UNKNOWN, 1=DISCONNECTED, 2=CONNECTED
			local status = 0
			if heartbeat <= -10 then
				status = 1
				heartbeat = 1
			elseif heartbeat <= 0 then
				status = 0
				heartbeat = heartbeat - 1
			elseif heartbeat < frame.time.utc() - 10 then
				status = 1
				if cameraState ~= 0 then
					cameraState = 2
				end
				if micState >= 3 then
					micState = 2
					frame.microphone.stop()
				end
			else
				status = 2
				if cameraState == 2 then
					cameraState = 3
				end
				if micState == 2 then
					micState = 3
				end
				pcall(frame.bluetooth.send, '\xCC' .. string.char(battery))
			end
			if prevStatus ~= status then
				statusDisplayStartTime = frame.time.utc()
			end
			if statusDisplayStartTime > frame.time.utc() - 10 then
				frame.display.text('Battery: ' .. battery .. '%', 10, 10, {
					color = "GREY"
				})
				if status == 1 then
					frame.display.text('DISCONNECTED from Omi app', 10, 70, {
						color = "RED"
					})
				elseif status == 2 then
					frame.display.text('CONNECTED to Omi app', 10, 70, {
						color = "GREY"
					})
				end
				if frame.time.utc() > 10000 then
					local time_now = frame.time.date();
					local ampm = "am"
					local hour = time_now['hour']
					if hour > 12 then
						ampm = "pm"
						hour = hour - 12
					elseif hour == 0 then
						hour = 12
					end
					frame.display.text(hour .. ':' .. padNumber(time_now['minute'],2) .. ' ' .. ampm, 300, 160);
					frame.display.text(time_now['month'] .. '-' .. padNumber(time_now['day'],2) .. '-' .. time_now['year'], 300, 220)
				end
				if micState == 4 then
					frame.display.text('Recording', 10, 340, {
						color = "GREY"
					})
				end
				frame.display.show();
				showStatus = true
			else
				if showStatus then
					frame.display.text(' ', 10, 10)
					frame.display.show()
					showStatus = false
				end
			end
			prevStatus = status
		end
		-- cameraState: 0 = stopped, 1 = running, 2 = paused, 3 = exposing, 4 = capture, 5 = wait, 6 = send, 7 = done, 8 = waiting for next photo, 9 = waking up
		if cameraState == 3 then
			if autoExpTimeDelay == nil then
				cameraState = 4
			else
				if frame.time.utc() - lastAutoExpTime > 0.1 then
					frame.camera.auto({
						metering = 'CENTER_WEIGHTED'
					})
					lastAutoExpTime = frame.time.utc()
				end
				if frame.time.utc() > cameraStateTime + autoExpTimeDelay then
					cameraState = 4
				end
			end
		elseif cameraState == 4 then
			frame.camera.capture({
				photoQuality_factor = photoQuality
			})
			cameraStateTime = frame.time.utc()
			cameraState = 5
		elseif cameraState == 5 then
			if frame.time.utc() > cameraStateTime + 0.4 then
				cameraState = 6
			end
		elseif cameraState == 6 then
			if queuedCameraData ~= nil then
				if pcall(frame.bluetooth.send, queuedCameraData) then
					queuedCameraData = nil
				end
			else
				local i = frame.camera.read_raw(maxDataLen)
				if (i == nil or i == '') then
					cameraState = 7
				else
					cameraStateTime = frame.time.utc()
					if not pcall(frame.bluetooth.send, '\x07' .. i) then
						queuedCameraData = '\x07' .. i
					end
					photoChunkIndex = photoChunkIndex + 1
				end
			end
		elseif cameraState == 7 then
			if queuedCameraData ~= nil then
				if pcall(frame.bluetooth.send, queuedCameraData) then
					queuedCameraData = nil
				end
			else
				if not pcall(frame.bluetooth.send, '\x08' .. photoChunkIndex) then
					queuedCameraData = '\x08' .. photoChunkIndex
				end
			end
			if queuedCameraData == nil then
				photoChunkIndex = 0
				cameraStateTime = frame.time.utc()
				cameraState = 8
				--micResume()
			end
		elseif cameraState == 8 then
			if frame.time.utc() > cameraStateTime + delayBetweenPhotos - 0.5 - autoExpTimeDelay then
				cameraStateTime = frame.time.utc()
				cameraState = 3
			end
		elseif cameraState == 9 then
			if frame.time.utc() - cameraStateTime > 1 then
				cameraStateTime = frame.time.utc()
				cameraState = 3
			end
		end
		-- micState: 0 = stopped, 1 = n/a, 2 = paused, 3 = starting, 4 = sending, 5 = waiting for mic to reset
		if micState == 3 then
			micData = frame.time.utc()
			print("FrameLib mic STARTING -> waiting for mic to reset.  sampleRate=" .. sampleRate .. ", bitDepth=" .. bitDepth)
			frame.microphone.stop()
			micState = 5
		elseif micState == 5 and frame.time.utc() - micData > 0.2 then
			micData = nil
			print("FrameLib mic waiting for mic to reset -> SEND.")
			frame.microphone.start({
				sample_rate = sampleRate,
				bit_depth = bitDepth
			})
			micState = 4
		elseif micState == 4 then
			micLoops = 0
			while micLoops < 500 do
				micLoops = micLoops + 1
				micData = frame.microphone.read(maxDataLen)
				if micData == nil then break end
				if micData ~= '' then
					local lenMicData = #micData
					audioChunkIndex = audioChunkIndex + 1
					if audioChunkIndex > 65535 then
						audioChunkIndex = 0
					end
					local chunk_count_byte1 = audioChunkIndex % 256
					local chunk_count_byte2 = math.floor(audioChunkIndex / 256)

					if maxDataLen > lenMicData then
						if not pcall(frame.bluetooth.send, '\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. '\x00' .. micData) then
							-- try a second time.  If this fails, we'll just drop the data
							pcall(frame.bluetooth.send, '\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. '\x00' .. micData)
						end
						micData = nil
						if lenMicData < maxDataLen / 2 then
							micLoops = 9999
						end
					else
						local partial_index = 0
						local partial_chunk = string.sub(micData, 1, maxDataLen)
						while true do
							if not pcall(frame.bluetooth.send, '\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. string.char(partial_index) .. partial_chunk) then
								-- try a second time.  If this fails, we'll just drop the data
								pcall(frame.bluetooth.send, '\xEE' .. string.char(chunk_count_byte1) .. string.char(chunk_count_byte2) .. string.char(partial_index) .. partial_chunk)
							end
							partial_index = partial_index + 1
							micData = string.sub(micData, maxDataLen + 1)
							if micData == '' then
								break
							end
						end
					end
				end
			end
		end

	end
	print("FrameLib mainLoop() done")
end
function on_double_tap()
	statusDisplayStartTime = 0
end
function on_tap()
	local timeBetweenTaps = frame.time.utc() - lastTapTime	
	if timeBetweenTaps > 0.1 and timeBetweenTaps < 0.5 then
		on_double_tap()
	else
		statusDisplayStartTime = frame.time.utc()
	end
	if timeBetweenTaps > 0.05 then
		lastTapTime = frame.time.utc()
	end
end
function start()
	--frame.camera.sleep()
	cameraState = 0
	micState = 0
	loopStatus = 1
	lastTapTime = 0
	heartbeat = 0
	localHeartbeat = frame.time.utc()
	photoQuality = 25
	autoExpTimeDelay = 5
	delayBetweenPhotos = 15
	sampleRate = 8000
	bitDepth = 16
	statusDisplayStartTime = frame.time.utc() + 5
	frame.microphone.stop()
	frame.bluetooth.receive_callback(receiveBluetoothData)
	frame.imu.tap_callback(on_tap)
	mainLoop()
end
