from pyexpat import model

from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os

load_dotenv()

def main():
    llm = ChatGroq(model=os.getenv("LLM_MODEL"),temperature=1)
    query = input(" Enter the question ")
    response = llm.invoke(query)
    print(response.content)

if __name__ == "__main__":
    main()


