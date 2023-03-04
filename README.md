# HotStone Robot

与 `ChatGPT` 对接使用 `gpt-3.5-turbo` 模块提供对话服务.

安装启动包：
```
$ pip install -r requirements.txt
```

Django 创建 Models:
```
$ python3 manage.py makemigrations
$ python3 manage.py migrate
```

Django 创建 User:(可选)
```
$ python3 manage.py createsuperuser
```

启动 Django：
```
$ python3 manage.py runserver 0.0.0.0:80
```

# 可选

可传递指令清空当前缓存:

```
@clean history

or

@清空历史
```

> 目的是由于 ChatGPT 可通过上下文回复消息, 当想要重新与 ChatGPT 聊天时需要输入上述指令.

传递指令继续当前缓存:

```
@current session

or

@继续会话
```

> 会话保持默认 10 分钟, 当超过十分钟时如还需要保持上述对话内容需要输入上述指令.