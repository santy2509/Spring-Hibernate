import collectd
import json

import requests
from IPy import IP
from requests import ConnectionError

CONFIGS = []

VERBOSE_LOGGING = False


def url_requests(method, url, headers, params):
    if method == "post":
        try:
            response = requests.post(url, data=params, headers=headers, verify=False)
        except ConnectionError as e:
            log_verbose('LOGIN_STATUS : Connection Refused %s: %s' % (url, e))
            return None, 404
        else:
            session_key = response.headers['Set-Cookie'].split(";")
            login_session_key = session_key[0]
            log_verbose('LOGIN_STATUS %s: %s' % (url, response.text))
        return login_session_key, response.status_code
    else:
        try:
            response = requests.get(url, headers=headers, verify=False)
        except ConnectionError as e:
            log_verbose('REQUEST_STATUS : Connection Refused %s: %s' % (url, e))
            return None, 404
        return response.text, response.status_code


def get_cloud_portal_status(conf):
    url_status = {}
    headers = {"Content-Type": "application/json"}
    gms_ip = conf['host']
    user = conf['user']
    password = conf['password']
    portal_urls = conf['portal_urls']
    gms_path = conf["gms_path"]
    if not portal_urls:
        url_list = []
    else:
        url_list = portal_urls.split(",")

    try:
        IP(gms_ip)
    except:
        collectd.error('Invalid GMS_IP passed')
        pass
    else:
        payload = {"user": user, "password": password}
        params = json.dumps(payload)
        login_url = 'https://{}/{}/{}' .format(gms_ip, gms_path, conf['login_path'])
        gms_session_key, login_status_code = url_requests("post", login_url, headers, params)

        if login_status_code == 200:
            params = None
            headers = {"Cookie": gms_session_key, "Content-Type": "application/json"}
            logout_url = 'https://{}/{}/{}' .format(gms_ip, gms_path, conf["logout_path"])
            appliance_info_url = 'https://{}/{}/{}' .format(gms_ip, gms_path, conf["appliance_info_path"])
            ws_status_url = 'https://{}/{}/{}' .format(gms_ip, gms_path, conf["ws_status_path"])

            appliance_info, appliance_status_code = url_requests("get", headers, appliance_info_url, params)
            log_verbose('Appliance Info: %s' % appliance_info)
            try:
                appliance_id_list = [config['id'] for config in json.loads(appliance_info)]
            except ValueError as e:
                log_verbose('No Json Object could be decoded from the response %s' % e)
                url_requests("get", headers, logout_url, params)
                url_status['appliance_ws_status'] = 404
                pass
            else:
                ws_status_url = "{}/{}" .format(ws_status_url, appliance_id_list[0])
                ws_status_response, ws_status_code = url_requests("get", headers, ws_status_url, params)
                log_verbose('WS_Status: %s' % ws_status_response)
                url_status['appliance_ws_status'] = ws_status_code
            url_requests("get", headers, logout_url, params)
        else:
            url_status['appliance_ws_status'] = login_status_code

    for url in url_list:
        response_text, response_status_code = url_requests("get", headers, url, params)
        url_status[url] = response_status_code
    return url_status


def configure_callback(conf):
    host = None
    user = None
    password = None
    portal_urls = None
    gms_path = None
    login_path = None
    logout_path = None
    appliance_info_path = None
    ws_status_path = None
    for node in conf.children:
        key = node.key.lower()
        val = node.values[0]
        if key == 'host':
            host = val
        elif key == 'user':
            user = val
        elif key == 'password':
            password = val
        elif key == 'portal_urls':
            portal_urls = val
        elif key == 'gms_path':
            gms_path = val
        elif key == 'login_path':
            login_path = val
        elif key == 'logout_path':
            logout_path = val
        elif key == 'appliance_info_path':
            appliance_info_path = val
        elif key == 'ws_status_path':
            ws_status_path = val
        elif key == 'verbose':
            global VERBOSE_LOGGING
            VERBOSE_LOGGING = bool(node.values[0]) or VERBOSE_LOGGING
        else:
            collectd.warning('gms_info plugin: Unknown Config key: %s.' % key)
            continue

    CONFIGS.append({'host': host, 'user': user, 'password': password, 'portal_urls': portal_urls, 'gms_path': gms_path,
                    'login_path': login_path, 'logout_path': logout_path, 'appliance_info_path': appliance_info_path,
                    'ws_status_path': ws_status_path})


def read_callback(data=None):
    for conf in CONFIGS:
        url_status = get_cloud_portal_status(conf)
        for key in url_status:
            metric = collectd.Values()
            metric.plugin = 'portal_monitor'
            metric.type = 'gauge'
            metric.type_instance = key
            metric.values = [url_status[key]]
            metric.dispatch()


def log_verbose(msg):
    if not VERBOSE_LOGGING:
        return
    collectd.info('cloud portal plugin [verbose]: %s' % msg)

collectd.register_config(configure_callback)
collectd.register_read(read_callback)
