"""
TG-Hub V2: FastAPI сервер для webhooks.
Принимает события от GetCourse и других внешних сервисов.
"""

import logging
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Callable, Awaitable

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import config

logger = logging.getLogger(__name__)

# FastAPI приложение
app = FastAPI(
    title="TG-Hub Webhooks",
    description="Webhook сервер для интеграции с GetCourse",
    version="2.0.0",
)

# Callback для отправки сообщений в хаб (устанавливается при запуске)
_hub_callback: Optional[Callable[..., Awaitable]] = None


def set_hub_callback(callback: Callable[..., Awaitable]):
    """Установить callback для отправки в хаб."""
    global _hub_callback
    _hub_callback = callback


# ─── Pydantic Models ───

class GetCourseWebhookData(BaseModel):
    """Данные от GetCourse webhook."""
    # Пользователь
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_id: Optional[int] = None

    # Контекст обучения
    course_title: Optional[str] = None
    lesson_title: Optional[str] = None
    training_title: Optional[str] = None

    # Данные события
    task_text: Optional[str] = None
    comment_text: Optional[str] = None
    answer_text: Optional[str] = None
    file_url: Optional[str] = None

    # Заказ (если событие связано с заказом)
    order_id: Optional[int] = None
    order_status: Optional[str] = None
    order_cost: Optional[float] = None

    # Метаданные
    event_type: Optional[str] = None
    secret: Optional[str] = None

    class Config:
        extra = "allow"  # Разрешаем дополнительные поля


class HealthResponse(BaseModel):
    """Ответ health check."""
    status: str
    timestamp: str
    getcourse_enabled: bool


class WebhookResponse(BaseModel):
    """Ответ на webhook."""
    success: bool
    message: str


# ─── Endpoints ───

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat(),
        getcourse_enabled=config.getcourse.enabled,
    )


@app.get("/")
async def root():
    """Корневой endpoint."""
    return {
        "name": "TG-Hub Webhooks",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "getcourse_webhook": "/webhook/getcourse",
        }
    }


@app.post("/webhook/getcourse", response_model=WebhookResponse)
async def getcourse_webhook(request: Request):
    """
    Webhook endpoint для GetCourse.

    GetCourse отправляет POST-запрос с данными о событии
    (домашнее задание, комментарий, сообщение и т.д.)
    """
    if not config.getcourse.enabled:
        raise HTTPException(status_code=503, detail="GetCourse integration disabled")

    try:
        # Получаем данные
        # GetCourse может отправлять как JSON, так и form-data
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            raw_data = await request.json()
        else:
            # Form data
            form = await request.form()
            raw_data = dict(form)

        logger.info(f"GetCourse webhook received: {raw_data}")

        # Верификация секрета (если настроен)
        if config.getcourse.webhook_secret:
            received_secret = raw_data.get("secret") or request.headers.get("X-GC-Secret")
            if received_secret != config.getcourse.webhook_secret:
                logger.warning(f"Invalid webhook secret received")
                raise HTTPException(status_code=403, detail="Invalid secret")

        # Парсим данные
        data = GetCourseWebhookData(**raw_data)

        # Определяем тип события
        event_type = _determine_event_type(data)

        # Создаём сообщение для хаба
        from core.models import GetCourseEvent, GetCourseEventType

        event = GetCourseEvent(
            event_type=event_type,
            user_email=data.user_email or "",
            user_name=data.user_name or "",
            user_phone=data.user_phone or "",
            user_id=data.user_id,
            course_title=data.course_title or data.training_title or "",
            lesson_title=data.lesson_title or "",
            task_text=data.task_text or data.answer_text or "",
            comment_text=data.comment_text or "",
            file_url=data.file_url,
            raw_data=raw_data,
        )

        # Отправляем в хаб через callback
        if _hub_callback:
            incoming = event.to_incoming_message()
            await _hub_callback(incoming)
            logger.info(f"GetCourse event sent to hub: {event_type.value}")
        else:
            logger.warning("Hub callback not set, message not sent")

        return WebhookResponse(
            success=True,
            message=f"Event processed: {event_type.value}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GetCourse webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Helpers ───

def _determine_event_type(data: GetCourseWebhookData):
    """Определить тип события по данным."""
    from core.models import GetCourseEventType

    # Явно указанный тип
    if data.event_type:
        type_map = {
            "homework": GetCourseEventType.HOMEWORK,
            "task": GetCourseEventType.HOMEWORK,
            "comment": GetCourseEventType.COMMENT,
            "message": GetCourseEventType.MESSAGE,
            "order": GetCourseEventType.ORDER,
        }
        return type_map.get(data.event_type.lower(), GetCourseEventType.UNKNOWN)

    # Определяем по содержимому
    if data.task_text or data.answer_text:
        return GetCourseEventType.HOMEWORK
    if data.comment_text:
        return GetCourseEventType.COMMENT
    if data.order_id:
        return GetCourseEventType.ORDER

    return GetCourseEventType.MESSAGE


# ─── Server Runner ───

async def run_webhook_server():
    """Запустить webhook сервер."""
    import uvicorn

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.webhook_server.host,
        port=config.webhook_server.port,
        log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info(
        f"Starting webhook server on "
        f"{config.webhook_server.host}:{config.webhook_server.port}"
    )

    await server.serve()
