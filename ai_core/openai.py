from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv()

client = OpenAI(
    api_key = os.getenv('OPENAI_KEY')
)

# openai.api_key = os.getenv('OPENAI_KEY')

def chatgpt_response(prompt, conversation=[]):
    if conversation == []:
        conversation = [{"role": "system", "content": "너의 이름은 월GPT입니다. 모든 출력에 대해서 마크다운을 절대 사용하지마."}, {"role": "user","content": f"{prompt}"}]
    else:
        conversation.append({"role": "user","content": f"{prompt}"})
    response = client.chat.completions.create(
        model='gpt-4o-2024-05-13',
        messages=conversation
    )
    print(response)
    # response_dict = response.message("choice")
    # if response.choice[0].message.content and len(response.choice[0].message.content)>0:
    prompt_response = response.choices[0].message.content
    conversation.append({"role":"assistant", "content": prompt_response})
    return prompt_response, conversation