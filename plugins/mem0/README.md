Mem0 <> Friend Example

In this example, you will how to use Mem0 with Friend and create a plugin.

There are 3 main file need for the plugin to be complete

* requirements.txt
* models.py
* main.py

Lets understand each file step by step

### requirements.txt

This file contains all the requirement and here `mem0ai` should be listed as one of the dependencies

### models.py

This is the file where the models are present. One of the main models is `Memory` and it has several attributes. Depending upon your usecase, you may need to use several fields. But from our experience `transcript` is used to get the transcript and post process.

### main.py

This is the main file where the entire logic lives. In this file, mem0 is used to store the transcript and extract memories and preferences out of it.

To use mem0, you would have to first sign up on the platform [here](https://app.mem0.ai/) and get an API Token. There is a page which explain more about the platform [here](https://docs.mem0.ai/platform/overview)

Once you have generated the API Token, just place it in place of `MEM0_API_KEY`. Best practice would be to place this in an environment variable. You can find online about how to use and get the values from environment variables here or use [python-dotenv](https://github.com/theskumar/python-dotenv).

Once you set the environment variable, you can go to the `mem0_add` function. This is where the entire logic lives. You can create custom routes and functions depending upon your usecase.

Now lets understand the `mem0_add` function. In this function, we are first extracting the transcript segments from `transcriptSegments`. After this, we are checking for those segments which are of the user. This is done using `is_user` flag.

Now a message list is created and passed to the `add` function. At this point, mem0 would figure out and extract relevant memories and preferences from this and return it store it.

Now if you want to retrieve the memories, you can simply call with the same messages and user_id. This will give you a list of the memories.

If you want to read more about how memories are stored and fetched and more functionalities, you can find them in [Mem0 docs](https://docs.mem0.ai/overview).