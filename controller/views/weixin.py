import hashlib
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from resources import models as ResourceModels
from HotstoneRobot import settings
from django.utils import timezone
from openai.error import InvalidRequestError
import time
import xmltodict
import openai
import datetime
import pytz
import json
openai.api_key = settings.OPENAI_KEY

# EIP
@csrf_exempt
def initializeWeChat(request):
    """对接微信公众号服务器
    # 验证服务器地址的有效性
    # 开发者提交信息后，微信服务器将发送GET请求到填写的服务器地址URL上，GET请求携带四个参数:
    # signature:微信加密, signature结合了开发者填写的token参数和请求中的timestamp参数 nonce参数
    # timestamp:时间戳(chuo这是拼音)
    # nonce: 随机数
    # echostr: 随机字符串
    """
    return_response = {"code": -1, "items": []}

    # 接收微信服务器发送参数
    signature = request.GET.get("signature", default="")
    timestamp = request.GET.get("timestamp", default="")
    nonce = request.GET.get("nonce", default="")
    # 校验参数
    # 校验流程：
    # 将token、timestamp、nonce三个参数进行字典序排序
    # 将三个参数字符串拼接成一个字符串进行sha1加密
    # 开发者获得加密后的字符串可与signature对比，标识该请求来源于微信

    if not all([signature, timestamp, nonce]):
        return_response["code"] = 0
        return_response["Message"] = "传递无效的值!"
        return JsonResponse(return_response)

    # 按照微信的流程计算签名
    li = [settings.WECHAT_TOKEN, timestamp, nonce]

    # 排序
    li.sort()

    # 拼接字符串
    tmp_str = "".join(li)

    # 进行sha1加密, 得到正确的签名值
    sign = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()

    # 将自己计算的签名值, 与请求的签名参数进行对比, 如果相同, 则证明请求来自微信
    if signature != sign:
        # 代表请求不是来自微信
        # 弹出报错信息, 身份有问题
        return_response["code"] = 0
        return_response["Message"] = "无效的身份验证!"
        return JsonResponse(return_response)
    else:
        # 表示是微信发送的请求
        if request.method == "GET":
            # 表示第一次接入微信服务器的验证
            echostr = request.GET.get("echostr", default="")
            # 校验echostr
            return HttpResponse(echostr)

        elif request.method == "POST":
            # 表示微信服务器转发消息过来
            # 拿去xml的请求数据
            try:
                postBody = str(request.body, encoding="utf-8")
            except Exception as err:
                return_response["Message"] = "数据格式不是标准 Json {}".format(err)
                return JsonResponse(return_response)

            # 对xml字符串进行解析成字典
            xml_dict = xmltodict.parse(postBody)

            xml_dict = xml_dict.get("xml")

            # MsgType是消息类型 这里是提取消息类型
            msg_type = xml_dict.get("MsgType")

            # 获取数据库中是否有过此用户的交互记录
            _check_db_open_id = ResourceModels.UserCache.objects.filter(openid=xml_dict["FromUserName"])

            # 设置 ChatGPT 角色
            isRole = xml_dict.get("Content").strip().split("%")
            if len(xml_dict.get("Content").strip().split("%")) == 3:
                ChatGPT_Role = isRole[1]
            else:
                ChatGPT_Role = ""

            # 如果不存在需创建
            if not _check_db_open_id.exists():
                _insert_data = {
                    "context": json.dumps([{"role": "system", "content": ChatGPT_Role}]),
                    "openid": xml_dict.get("FromUserName"),
                }
                _check_db_insert_open_id = ResourceModels.UserCache.objects.create(**_insert_data)
                time.sleep(1)
            else:
                _check_db_insert_open_id = ResourceModels.UserCache.objects.get(openid=xml_dict.get("FromUserName"))
                if xml_dict.get("Content") == "@clean history" or xml_dict.get("Content") == "@清空历史":
                    ResourceModels.UserCache.objects.filter(openid=xml_dict.get("FromUserName")).delete()

                    resp_dict = {
                        "xml": {
                            "ToUserName": xml_dict.get("FromUserName"),
                            "FromUserName": xml_dict.get("ToUserName"),
                            "CreateTime": int(time.time()),
                            "MsgType": "text",
                            "Content": "已清空历史!"
                        }
                    }
                    # 将字典转换为xml字符串
                    resp_xml_str = xmltodict.unparse(resp_dict)
                    # 返回消息数据给微信服务器
                    return HttpResponse(resp_xml_str)

            # 避免重复的消息（可能存在微信超时后发送重复消息, 避免 Token 过大）
            if _check_db_insert_open_id.message == xml_dict.get("Content").strip():
                message = json.loads(_check_db_insert_open_id.context)

                if message[len(message) - 2]["role"] == "user" and message[len(message) - 2]["content"] == xml_dict.get("Content").strip():

                    resp_dict = {
                        "xml": {
                            "ToUserName": xml_dict.get("FromUserName"),
                            "FromUserName": xml_dict.get("ToUserName"),
                            "CreateTime": int(time.time()),
                            "MsgType": "text",
                            "Content": message[len(message) - 1]["content"]
                        }
                    }
                    # 将字典转换为xml字符串
                    resp_xml_str = xmltodict.unparse(resp_dict)
                    # 返回消息数据给微信服务器
                    return HttpResponse(resp_xml_str)

            # 判断会话时间, 默认超过 10 分钟则开启新会话
            if (xml_dict.get("Content") != "@current session" or xml_dict.get("Content") != "@继续会话") and (datetime.datetime.now(pytz.timezone(settings.TIME_ZONE)) - _check_db_insert_open_id.timestamp).seconds >= 600:
                messages = [{"role": "system", "content": ChatGPT_Role}]
                messages.append({"role": "user", "content": xml_dict.get("Content").strip()})
                try:
                    completion = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages
                    )
                    # 当正常发送时修改数据库
                    messages.append(
                        {"role": "assistant", "content": completion["choices"][0]["message"]["content"].strip()})
                    _check_db_insert_open_id.context = json.dumps(messages)
                    _check_db_insert_open_id.timestamp = timezone.now()
                    _check_db_insert_open_id.message = xml_dict.get("Content").strip()
                    _check_db_insert_open_id.save()
                except InvalidRequestError:
                    ResourceModels.UserCache.objects.filter(openid=xml_dict["FromUserName"]).delete()
                    resp_dict = {
                        "xml": {
                            "ToUserName": xml_dict.get("FromUserName"),
                            "FromUserName": xml_dict.get("ToUserName"),
                            "CreateTime": int(time.time()),
                            "MsgType": "text",
                            "Content": "因达到 ChatGPT 4096 限制, 已经重置会话, 请重新发起对话内容!"
                        }
                    }
                    # 将字典转换为xml字符串
                    resp_xml_str = xmltodict.unparse(resp_dict)
                    # 返回消息数据给微信服务器
                    return HttpResponse(resp_xml_str)

            else:
                messages = json.loads(_check_db_insert_open_id.context)
                messages.append({"role": "user", "content": xml_dict.get("Content").strip()})
                try:
                    completion = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=messages
                    )
                    # 当正常发送时修改数据库
                    messages.append(
                        {"role": "assistant", "content": completion["choices"][0]["message"]["content"].strip()})
                    _check_db_insert_open_id.context = json.dumps(messages)
                    _check_db_insert_open_id.timestamp = timezone.now()
                    _check_db_insert_open_id.message = xml_dict.get("Content").strip()
                    _check_db_insert_open_id.save()
                except InvalidRequestError:
                    ResourceModels.UserCache.objects.filter(openid=xml_dict["FromUserName"]).delete()
                    resp_dict = {
                        "xml": {
                            "ToUserName": xml_dict.get("FromUserName"),
                            "FromUserName": xml_dict.get("ToUserName"),
                            "CreateTime": int(time.time()),
                            "MsgType": "text",
                            "Content": "因达到 ChatGPT 4096 限制, 已经重置会话, 请重新发起对话内容!"
                        }
                    }
                    # 将字典转换为xml字符串
                    resp_xml_str = xmltodict.unparse(resp_dict)
                    # 返回消息数据给微信服务器
                    return HttpResponse(resp_xml_str)
            print(completion)
            if msg_type == "text":
                # 表示发送文本消息
                # 第一次要么回复你想回复的内容, 不知道回复什么, 微信说了要么回复success, 要么空字符串
                # 够造返回值, 经由微信服务器回复给用户的消息内容
                # 回复消息
                # ToUsername: (必须传) 接收方账号(收到的OpenID)
                # FromUserName: (必须传) 开发者微信号
                # CreateTime: (必须传) 消息创建时间(整形)
                # MsgType: (必须传) 消息类型
                # Content: (必须传) 回复消息的内容(换行:在Content中能够换行, 微信客户端就支持换行显示)

                resp_dict = {
                    "xml": {
                        "ToUserName": xml_dict.get("FromUserName"),
                        "FromUserName": xml_dict.get("ToUserName"),
                        "CreateTime": int(time.time()),
                        "MsgType": "text",
                        "Content": completion["choices"][0]["message"]["content"].strip()
                    }
                }
            else:
                resp_dict = {
                    "xml": {
                        "ToUserName": xml_dict.get("FromUserName"),
                        "FromUserName": xml_dict.get("ToUserName"),
                        "CreateTime": int(time.time()),
                        "MsgType": "text",
                        "Content": "无效的内容"
                    }
                }
            # 将字典转换为xml字符串
            resp_xml_str = xmltodict.unparse(resp_dict)
            # 返回消息数据给微信服务器
            return HttpResponse(resp_xml_str)

    return JsonResponse(return_response)