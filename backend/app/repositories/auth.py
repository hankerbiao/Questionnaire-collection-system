from datetime import datetime


class UserAuthRepositoryMixin:
    async def consume_external_ticket(self, jti: str, expires_at: datetime) -> None:
        await self.consumed_external_tickets.insert_one(
            {"jti": jti, "expires_at": expires_at}
        )
