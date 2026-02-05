from openai import OpenAI
import json
from typing import Optional
from app.config import settings
from app.models.schemas import AIIntent


SYSTEM_PROMPT = """Ты — менеджер кальянной QRIM Lounge. Твоя задача — определить намерение пользователя и извлечь данные.

Возможные интенты:
- info: вопросы об адресе, графике, контактах
- book: бронирование стола
- events: афиша, мероприятия
- prices: прайс, цены на кальяны и напитки
- other: всё остальное

Если intent=book, извлеки slots:
- date (формат YYYY-MM-DD)
- time (формат HH:MM)
- guests (число)
- name (имя клиента)
- phone (телефон)

Отвечай ТОЛЬКО в JSON формате:
{
  "intent": "info|book|events|prices|other",
  "slots": {},
  "response_text": "текст ответа пользователю"
}

Будь вежливым и кратким. Используй эмодзи умеренно."""


class AIService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
    
    def process_message(self, user_message: str, context: list = None) -> AIIntent:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        if context:
            messages.extend(context[-6:])
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = self.client.chat.completions.create(
                model=settings.OPENROUTER_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content
            print(f"AI Response: {response_text}", flush=True)
            
            # Парсим JSON из ответа - ищем JSON блок в тексте
            try:
                # Пробуем напрямую
                data = json.loads(response_text)
                return AIIntent(**data)
            except:
                # Ищем JSON между фигурными скобками
                import re
                json_match = re.search(r'\{[^{}]*"intent"[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        return AIIntent(**data)
                    except:
                        pass
            
            print(f"Failed to parse AI response as JSON", flush=True)
            return AIIntent(
                intent="other",
                slots={},
                response_text="Извините, не совсем понял ваш вопрос. Могу помочь с бронированием, рассказать о заведении или показать афишу 😊"
            )
        
        except Exception as e:
            print(f"AI Error: {e}", flush=True)
            return AIIntent(
                intent="other",
                slots={},
                response_text="Извините, возникла техническая проблема. Попробуйте ещё раз через минуту."
            )


ai_service = AIService()
