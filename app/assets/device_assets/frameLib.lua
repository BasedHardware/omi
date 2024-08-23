function micPause()
	if micState == 4 or micState == 3 then
		micState = 2
		frame.microphone.stop()
	end
end
function micResume()
	if cameraState >= 4 and cameraState <= 7 then
	elseif micState == 2 then
		micState = 3
	end
end
function micStart()
	if micState == 0 or micState == 2 then
		if cameraState >= 4 and cameraState <= 7 then
			micState = 2
		else
			micState = 3
		end
	end
end

function receiveBluetoothData(data)
	if data ~= nil then
		local eqIdx = string.find(data, "=")
		if data == "CAMERA START" then
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
			micStart()
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
		elseif eqIdx ~= nil then
			local key = string.sub(data, 1, eqIdx - 1)
			local value = string.sub(data, eqIdx + 1)

			print("Setting " .. key .. " to " .. value)
			if key == "photoQuality" then
				local _photoQuality = tonumber(value)
				if _photoQuality and _photoQuality >= 0 and _photoQuality <= 100 then
					photoQuality = _photoQuality
				end
			elseif key == "autoExpTimeDelay" then
				local _autoExpTimeDelay = tonumber(value)
				if _autoExpTimeDelay and _autoExpTimeDelay >= 0 and _autoExpTimeDelay <= 10 then
					autoExpTimeDelay = _autoExpTimeDelay
				end
			elseif key == "autofocusType" then
				autofocusType = value
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
			elseif key == "silenceThreshold" then
				local _silenceThreshold = tonumber(value)
				if _silenceThreshold and _silenceThreshold >= 0 and _silenceThreshold <= 1 then
					silenceThreshold = _silenceThreshold
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

function mainLoop()
	heartbeat = frame.time.utc()
	if photoQuality == nil then
		photoQuality = 25
	end
	if autoExpTimeDelay == nil then
		autoExpTimeDelay = 2
	end
	if autofocusType == nil then
		autofocusType = 'AVERAGE'
	end
	if delayBetweenPhotos == nil then
		delayBetweenPhotos = 10
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
	if photoChunkIndex == nil then
		photoChunkIndex = 0
	end

	if audioChunkIndex == nil then
		audioChunkIndex = 0
	end

	local showStatus = true
	local micData = nil

	--loopStatus: 0 = stopped, 1 = running, 2 = paused
	loopStatus = 1
	local micLoops = 0
	lastStatusUpdate = 0
	didMicSend = 0
	local queuedCameraData = nil
	local queuedMicData = nil

	local maxDataLen = frame.bluetooth.max_length() - 5

	if maxDataLen % 2 ~= 0 then
		maxDataLen = maxDataLen - 1
	end

	print("maxDataLen = " .. maxDataLen)

	while loopStatus == 1 do
		localHeartbeat = frame.time.utc()
		if lastStatusUpdate < frame.time.utc() - 1 then
			lastStatusUpdate = frame.time.utc()
			local battery = frame.battery_level()
			local status = 'UNKNOWN'
			if heartbeat < frame.time.utc() - 10 then
				status = 'DISCONNECTED'
				print("FrameLib status DISCONNECTED")
				
				if cameraState ~= 0 then
					cameraState = 2
				end
				micPause()
				if frame.time.utc() - heartbeat < 20 then
					statusDisplayStartTime = frame.time.utc()
				end
			else
				status = 'CONNECTED'
				if cameraState == 2 then
					cameraState = 3
				end
				micResume()

				pcall(frame.bluetooth.send, '\xCC' .. string.char(battery))
			end
			if statusDisplayStartTime > frame.time.utc() - 10 then
				frame.display.text('Battery: ' .. battery .. '%', 10, 10, {
					color = "GREY"
				})
				if status == 'DISCONNECTED' then
					frame.display.text('DISCONNECTED from Friend app', 10, 70, {
						color = "RED"
					})
				elseif status == 'CONNECTED' then
					frame.display.text('CONNECTED to Friend app', 10, 70, {
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
					frame.display.text(tostring(hour) .. ':' .. tostring(time_now['minute']) .. ' ' .. ampm, 300, 160);
					frame.display.text(tostring(tonumber(time_now['month'])) .. ' / ' .. tostring(tonumber(time_now['day'])) .. ' / ' .. time_now['year'], 300, 220)
				end
				frame.display.text('Photos: ' .. photosSent, 10, 280, {
					color = "GREY"
				})
				local audioText = ''
				if micState == 4 then
					audioText = 'Audio: recording'
				end
				if didMicSend > 0 then
					frame.display.text(audioText, 10, 340, {
						color = "GREEN"
					})
				else
					frame.display.text(audioText, 10, 340, {
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
			didMicSend = 0
		end
		-- cameraState: 0 = stopped, 1 = running, 2 = paused, 3 = exposing, 4 = capture, 5 = wait, 6 = send, 7 = done, 8 = waiting for next photo, 9 = waking up
		if cameraState == 3 then
			if autoExpTimeDelay == nil then
				cameraState = 4
				--micPause()
			else
				if frame.time.utc() - lastAutoExpTime > 0.1 then
					frame.camera.auto({
						metering = autofocusType
					})
					lastAutoExpTime = frame.time.utc()
				end
				if frame.time.utc() > cameraStateTime + autoExpTimeDelay then
					cameraState = 4
					--micPause()
				end
			end
		elseif cameraState == 4 then
			--micPause()
			frame.camera.capture({
				photoQuality_factor = photoQuality
			})
			cameraStateTime = frame.time.utc()
			cameraState = 5
		elseif cameraState == 5 then
			--micPause()
			if frame.time.utc() > cameraStateTime + 0.4 then
				cameraState = 6
			end
		elseif cameraState == 6 then
			--micPause()
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
				photosSent = photosSent + 1
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
		-- micState: 0 = stopped, 1 = n/a, 2 = paused, 3 = starting, 4 = sending
		if micState == 3 then
			print("FrameLib mic STARTING -> SEND.  sampleRate=" .. sampleRate .. ", bitDepth=" .. bitDepth)
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
						micData = ''
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
	heartbeat = frame.time.utc()
	localHeartbeat = frame.time.utc()
	photoQuality = 25
	autoExpTimeDelay = 5
	autofocusType = 'CENTER_WEIGHTED'
	delayBetweenPhotos = 15
	sampleRate = 8000
	bitDepth = 16
	--noiseFloor = 0
	--silenceThreshold = 0.01
	photosSent = 0
	statusDisplayStartTime = frame.time.utc() + 5
	print("FrameLib start() Version 9")
	frame.microphone.stop()
	frame.bluetooth.receive_callback(receiveBluetoothData)
	frame.imu.tap_callback(on_tap)
	print("FrameLib start() B")
	mainLoop()
	print("FrameLib start() done")
end

start()