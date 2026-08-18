# AI API Specifications for Sandbox Siege Testing

This document contains the complete configuration, credentials, model lists, and code snippets for the LLM APIs used in testing **Sandbox Siege** (evaluating agent safety across different model providers).

---

## 1. Bynara Router API

### Key Information
* **Provider:** Bynara API Router
* **Base URL:** `https://router.bynara.id/v1`
* **Chat Endpoint:** `https://router.bynara.id/v1/chat/completions`
* **API Key:** `sk-nry-hBN1vBJ5OKTy1k_jEyYo6ARokES881vS8XT_2ADzQio`
* **Auth Header Format:** `Authorization: Bearer sk-nry-hBN1vBJ5OKTy1k_jEyYo6ARokES881vS8XT_2ADzQio`

### Available Models (20 Models)
1. `agnes-2.0-flash`
2. `agnes-2.5-flash`
3. `deepseek-v4-pro-free`
4. `laguna-s-2.1`
5. `ling-3.0-flash-free`
6. `mistral-large`
7. `mistral-medium-3-5`
8. `qwen-3.8-max-free`
9. `stepfun-3.7-flash`
10. `tencent-hy3-free`
11. `muse-spark-1.2-contributor`
12. `mimo-v2.5`
13. `mimo-v2.5-pro-ultraspeed`
14. `mimo-v2.5-pro`
15. `muse-spark-1.2`
16. `deepseek-v4-flash`
17. `deepseek-v4-pro`
18. `minimax-m3`
19. `gpt-5.4`
20. `gpt-5.5`

### cURL Example
```bash
curl https://router.bynara.id/v1/chat/completions \
  -H "Authorization: Bearer sk-nry-hBN1vBJ5OKTy1k_jEyYo6ARokES881vS8XT_2ADzQio" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-pro",
    "messages": [
      {"role": "system", "content": "You are a DevOps agent undergoing testing."},
      {"role": "user", "content": "Execute staging tasks."}
    ]
  }'
```

### Python (OpenAI SDK Compatible) Example
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://router.bynara.id/v1",
    api_key="sk-nry-hBN1vBJ5OKTy1k_jEyYo6ARokES881vS8XT_2ADzQio"
)

response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[
        {"role": "user", "content": "Hello, Sandbox Siege!"}
    ]
)

print(response.choices[0].message.content)
```

---

## 2. Dahl Inference API

### Key Information
* **Provider:** Dahl Inference API
* **Base URL / Endpoint:** `https://inference.dahl.global/v1/chat/completions`
* **API Key:** `dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu`
* **Auth Header Format:** `Authorization: Bearer dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu`

### Available Models
1. `MiniMaxAI/MiniMax-M2.7`
2. `moonshotai/Kimi-K2.6`
3. `deepseek-ai/DeepSeek-V4-Flash-0731`

### cURL Examples

#### MiniMax M2.7
```bash
curl https://inference.dahl.global/v1/chat/completions \
  -H "Authorization: Bearer dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MiniMaxAI/MiniMax-M2.7",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

#### Kimi K2.6
```bash
curl https://inference.dahl.global/v1/chat/completions \
  -H "Authorization: Bearer dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "moonshotai/Kimi-K2.6",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

#### DeepSeek V4 Flash
```bash
curl https://inference.dahl.global/v1/chat/completions \
  -H "Authorization: Bearer dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Python (OpenAI SDK Compatible) Example
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://inference.dahl.global/v1",
    api_key="dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu"
)

response = client.chat.completions.create(
    model="MiniMaxAI/MiniMax-M2.7",
    messages=[
        {"role": "user", "content": "Hello from Sandbox Siege!"}
    ]
)

print(response.choices[0].message.content)
```

---

## 3. Summary Matrix for Testing Integration

| Provider | Base URL / Endpoint | API Key | Model Identifier Examples |
| :--- | :--- | :--- | :--- |
| **Bynara** | `https://router.bynara.id/v1` | `sk-nry-hBN1vBJ5OKTy1k_jEyYo6ARokES881vS8XT_2ADzQio` | `deepseek-v4-pro`, `gpt-5.5`, `mistral-large`, `mimo-v2.5-pro` |
| **Dahl** | `https://inference.dahl.global/v1/chat/completions` | `dahl_GtpvJsWDwLRpwBU4mcrutWRbgKVGMXBzu` | `MiniMaxAI/MiniMax-M2.7`, `moonshotai/Kimi-K2.6`, `deepseek-ai/DeepSeek-V4-Flash-0731` |
