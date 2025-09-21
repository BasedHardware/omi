# pip install mem0ai --no-deps
# Not implementing for now, would be to overcomplicate and slow things down.

# from mem0 import Memory as Mem0Memory
#
# from _shared import *
#
# client = Mem0Memory()
#
#
# def store():
#     # result = m.add("Likes to play cricket on weekends", user_id="alice", metadata={"category": "hobbies"})
#     memories = get_memories()
#     data = Memory(**memories[0])
#     item = client.add(Memory.memories_to_string([data]), user_id=uid, metadata={"category": "hobbies"})
#     print(item)
#
#
# def search():
#     client.search("Who am I?")
#
#
# if __name__ == '__main__':
#     store()
