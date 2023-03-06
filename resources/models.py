from django.db import models
from django.contrib.auth.models import User, Permission, Group
from django.utils import timezone
import uuid

class UserCache(models.Model):

    uuid = models.CharField(max_length=128, verbose_name="uuid", default=uuid.uuid1())
    context = models.TextField(verbose_name="上下文", null=True, blank=True)
    openid = models.CharField(max_length=64, verbose_name="OpenID", null=False, blank=False, unique=False)
    message = models.CharField(max_length=256, verbose_name="发送的消息", null=True, blank=True)
    timestamp = models.DateTimeField(verbose_name="触发时间", null=False, default=timezone.now)

    def __str__(self):
        return self.openid