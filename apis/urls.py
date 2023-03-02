from django.urls import re_path
from controller.views import (
    weixin
)

urlpatterns = [
    re_path('^v1/weixin/receive', weixin.initializeWeChat, name="weixin-receive")
]