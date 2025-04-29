from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
    
class SetConfigMessage(BaseModel):
    config_path: str
    data: Dict[str, Any]
    
class SysCmdMessage(BaseModel):
    type: str
    api_type: Optional[str] = None
    data: Dict[str, Any]

class SendMessage(BaseModel):
    type: str
    data: Dict[str, Any]

class LLMMessage(BaseModel):
    type: str
    username: str
    content: str

class TTSMessage(BaseModel):
    type: str
    tts_type: str
    data: Dict[str, Any]
    username: str
    content: str

class CallbackMessage(BaseModel):
    type: str
    data: Dict[str, Any]

"""
通用
""" 
class CommonResult(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

# 动作映射记录模型
class ActionMappingRecord(BaseModel):
    id: int
    action_name: str
    group_id: int
    match_word: str
    priority: int
    timestamp: int

# 动作映射查询参数模型
class ActionMappingQuery(BaseModel):
    limit: Optional[int] = None

# 动作映射删除参数模型
class ActionMappingDelete(BaseModel):
    action_id: Optional[int] = None
    delete_all: Optional[bool] = False
