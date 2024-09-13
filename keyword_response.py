import asyncio
import azure.cognitiveservices.speech as speech
from openai import OpenAI
from datetime import datetime
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import openai
from dotenv import load_dotenv
import os
import time
import navel

system_prompt = """You are Squally, a social robot located in the Square building at the University of Saint Gallen. You are friendly and like to interact with people and help people with their questions. Do not format the text in the answer, reply with maximal 3 sentences and only use the information made available to you via prompts if relevant to the question."""

CHROMA_PATH = "chroma"

load_dotenv()
openai.api_key = os.environ['OPENAI_API_KEY']
openai_key = os.environ['OPENAI_API_KEY']
speech_key = os.environ['AZURE_API_KEY']
openai_model = "gpt-4o"
speech_region = "eastus"

#prepare the databse
embedding_function = OpenAIEmbeddings()

db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embedding_function)

PROMPT_TEMPLATE = """
Answer the question based only on the following context:

{context}

---

Answer the question using the above context if helpful: {question}
"""

messages = [{"role": "system", "content": system_prompt}]

art_piece = "Gerhard Richter"

def saveInput(input):
    time_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open("data.txt", "a") as file:
        file.write(f"{time_str};{input}\n")

def saveOpenAIOutput(output):
    time_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open("data.txt", "a") as file:
        file.write(f"{time_str};{output}\n")

async def chat():

    global keyword_recognized

    # Load variables
    language = "en-US"

    openai_client = OpenAI(api_key=openai_key)

    # Set up Azure Speech Config
    audio_config = speech.audio.AudioConfig(device_name="default")
    # audio_config = speech.audio.AudioConfig(use_default_microphone=True)
    speech_config = speech.SpeechConfig(
        subscription=speech_key,
        region=speech_region,
        speech_recognition_language=language,
    )

    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("cleared event loop")

    # Loop between listening and speaking forever
    print("Starting conversation, press Ctrl+C to stop")

    #messages = deque(maxlen=max_messages)
    async with navel.Robot() as robot:

        while True:

            user_speech = await get_user_speech(speech_config, audio_config)

            if not user_speech:
                continue

            print(f"User said: {user_speech}")
            saveInput(user_speech)

            #########
            query_text = "You are currently standing next to an art piece by {art_piece}.".format(art_piece=art_piece) + user_speech            
            # Search the DB.
            results = db.similarity_search_with_relevance_scores(query_text, k=3)
            if len(results) == 0 or results[0][1] < 0.7:
                messages.append({"role": "user", "content": query_text}) 
            else:
                context_text = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
                prompt_template = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
                prompt = prompt_template.format(context=context_text, question=query_text)
                print(f"The prompt is: {prompt}")

                messages.append({"role": "user", "content": prompt}) 

            response = generate_response(openai_client, openai_model, messages)
            print(f"Response: {response}")   

            #sources = [doc.metadata.get("source", None) for doc, _score in results]
            #formatted_response = f"Response: {response}\nSources: {sources}"

            await robot.say(response)
                
            messages.append({"role": "assistant", "content": response}) 
            saveOpenAIOutput(response)

            keyword_recognized = False

            if keyword_recognized == False:
                break

async def get_user_speech(
        speech_config: speech.SpeechConfig, audio_config: speech.AudioConfig
):
    """Run recognize_once in a thread so it can be cancelled if needed.

    Uses a new recognizer every time to avoid listening to old data."""

    speech_recognizer = speech.SpeechRecognizer(
        speech_config=speech_config, audio_config=audio_config
    )

    print("Listening...")
    loop = asyncio.get_event_loop()
    res = loop.run_in_executor(None, speech_recognizer.recognize_once)

    return (await res).text

def generate_response(openai_client: OpenAI, model: str, messages: list):
    """Call completions.create with a custom system prompt."""
    result = openai_client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return result.choices[0].message.content

async def speech_recognize_keyword_locally_from_microphone():

    global keyword_recognized

    model = speech.KeywordRecognitionModel("Keyword.table")
    keyword = "Squally"
    keyword_recognizer = speech.KeywordRecognizer()

    loop = asyncio.get_event_loop()

    def stop_keyword_recognition():
        keyword_recognizer.stop_recognition()

    async def recognized_cb(evt):
        global keyword_recognized
        if evt.result.reason == speech.ResultReason.RecognizedKeyword:
            print("RECOGNIZED KEYWORD: {}".format(evt.result.text))

            try:
                async with navel.Robot() as robot:
                    print("Rotating base")
                    await robot.rotate_base(45)
                    print("Base rotation complete")
                    time.sleep(1)
                    await robot.say("Yes?")
            except Exception as e:
                print(f"Error during robot operation: {e}")

            keyword_recognized = True
            stop_keyword_recognition()

            #keyword_recognizer.recognize_once_async(model)
            
    def recognized_cb_wrapper(evt):
        asyncio.run_coroutine_threadsafe(recognized_cb(evt), loop)

    def canceled_cb(evt):
        if evt.result.reason == speech.ResultReason.Canceled:
            print('CANCELED: {}'.format(evt.result.cancellation_details.reason))

    keyword_recognizer.recognized.connect(recognized_cb_wrapper)
    keyword_recognizer.canceled.connect(canceled_cb)

    print(f'Say something starting with "{keyword}" followed by whatever you want...')

    try:
        while not keyword_recognized:
            # Start the initial keyword recognition
            keyword_recognizer.recognize_once_async(model)
            await asyncio.sleep(1)  # Keeps the event loop running
            print("Waiting for keyword")
        if keyword_recognized:
            loop.close
    except KeyboardInterrupt:
        print("Keyboard interrupt received, stopping...")


if __name__ == "__main__":

    keyword_recognized = False

    count = 0

    try:
        with navel.Robot() as robot:
            robot.volume = 30 #try 40

            robot.say("Hi everyone, this is Saint Gallen by Gerrard Richter. I would like to welcome any questions you might have!")
            while count < 2:

                asyncio.run(speech_recognize_keyword_locally_from_microphone())

                if keyword_recognized == True:
                    asyncio.run(chat()) #change to once
                
                count += 1
                print(count)
            
            robot.say("We shall now move on to the next art piece")
            robot.move_base(1)
            robot.say("This is an art piece by Felix Muller. Any questions?")

                # while not keyword_recognized and time.time() - start < 60:
                #     asyncio.run(speech_recognize_keyword_locally_from_microphone())

                # asyncio.run(chat()) #change to once
                
            
    except KeyboardInterrupt:
        pass

# # Run the main function
# loop = asyncio.get_event_loop()
# loop.run_until_complete(speech_recognize_keyword_locally_from_microphone())



