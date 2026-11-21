from openai import OpenAI
import os


def _load_local_env():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    env_path = os.path.join(base_dir, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_local_env()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())

try:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY not found in environment/.env")
    # Attempt to list models as a simple validation check
    models = client.models.list()
    print("Success! Your OpenAI API key is valid.")
    print(f"First 3 available models: {[m.id for m in models.data[:3]]}")
except Exception as e:
    print(f"Error testing API key: {e}")
