import csv
import os
import aiohttp
from typing import Optional, List, Dict


class FeishuNotifier:
    def __init__(self, config_dir: str = "config", logger=None):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "FeiShu.csv")
        self.logger = logger
        self.configs = self._load_configs()
    
    def _load_configs(self) -> List[Dict]:
        if not os.path.exists(self.config_file):
            if self.logger:
                self.logger.warning(f"飞书配置文件不存在: {self.config_file}")
            return []
        
        configs = []
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    configs.append({
                        'tag': row['tag'],
                        'url': row['url'],
                        'mode': row['mode']
                    })
            if self.logger:
                self.logger.info(f"加载飞书配置 {len(configs)} 条")
        except Exception as e:
            if self.logger:
                self.logger.error(f"加载飞书配置失败: {str(e)}")
        return configs
    
    def _build_message(self, v_body: str, v_title: Optional[str] = None) -> dict:
        if v_title is None:
            return {
                "msg_type": "text",
                "content": {"text": v_body}
            }
        else:
            return {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh-CN": {
                            "title": v_title,
                            "content": [
                                [{"tag": "text", "text": v_body}]
                            ]
                        }
                    }
                }
            }
    
    async def _send_to_webhook(self, session: aiohttp.ClientSession, url: str, message: dict) -> bool:
        try:
            async with session.post(url, json=message) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('StatusCode') == 0:
                        if self.logger:
                            self.logger.info(f"飞书消息发送成功")
                        return True
                    else:
                        if self.logger:
                            self.logger.error(f"飞书消息发送失败: {result}")
                        return False
                else:
                    if self.logger:
                        self.logger.error(f"飞书消息发送失败，状态码: {response.status}")
                    return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"飞书消息发送异常: {str(e)}")
            return False
    
    async def send_message(self, v_body: str, v_title: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, bool]:
        results = {}
        
        if not self.configs:
            if self.logger:
                self.logger.warning("无飞书配置，跳过发送")
            return results
        
        async with aiohttp.ClientSession() as session:
            for config in self.configs:
                config_tag = config['tag']
                config_url = config['url']
                config_mode = config['mode']
                
                if tag and config_tag != tag:
                    continue
                
                if config_mode == 'none':
                    results[config_tag] = True
                    if self.logger:
                        self.logger.info(f"飞书机器人 [{config_tag}] 模式为 none，跳过发送")
                    continue
                
                if config_mode == 'text':
                    message = self._build_message(v_body, v_title=None)
                elif config_mode == 'post':
                    message = self._build_message(v_body, v_title=v_title)
                elif config_mode == 'title':
                    message = self._build_message(v_body, v_title=v_title)
                else:
                    if self.logger:
                        self.logger.warning(f"飞书机器人 [{config_tag}] 未知模式: {config_mode}")
                    results[config_tag] = False
                    continue
                
                success = await self._send_to_webhook(session, config_url, message)
                results[config_tag] = success
        
        return results
    
    async def send_to_all(self, v_body: str, v_title: Optional[str] = None) -> Dict[str, bool]:
        return await self.send_message(v_body, v_title)
    
    async def send_to_tag(self, tag: str, v_body: str, v_title: Optional[str] = None) -> bool:
        results = await self.send_message(v_body, v_title, tag=tag)
        return results.get(tag, False)


async def send_feishu_message(logger, v_body: str, v_title: Optional[str] = None, tag: Optional[str] = None) -> Dict[str, bool]:
    notifier = FeishuNotifier(logger=logger)
    return await notifier.send_message(v_body, v_title, tag)
