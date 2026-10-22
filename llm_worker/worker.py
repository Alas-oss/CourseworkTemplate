import os


O = os.getenv("OLLAMA_URL", "")
M = os.getenv("OLLAMA_CHAT_MODEL", "")
E = os.getenv("OLLAMA_EMBED_MODEL", "")

#To be completed

#Recommended prompt:
#"You are a concise game guide. "
#"Use only retrieved instructions "
#"and validated data. For hints "
#"give exactly one next step. "
#"Never invent state. Maximum "
#"45 words."
