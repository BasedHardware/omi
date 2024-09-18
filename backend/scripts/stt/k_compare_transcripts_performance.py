# STEPS
# - get all users
# - get all memories non discarded
# - filter memories with audio recording available
# - filter again by ones that have whisperx + deepgram segments or soniox segments
# - store local json with data

# - P2
# - read local json with each memory audio file
# - call whisper groq (whisper-largev3)
# - Create a table df, well printed, with each transcript result side by side
# - prompt for computing WER using groq whisper as baseline (if better, but most likely)
# - Run for deepgram vs soniox, and generate comparison result

# - P3
# - Include speechmatics to the game

