import time
import queue
import threading
from typing import Dict, List, Optional, Union, Any

class UnityQueueHandler:
    """
    Unity相关队列处理类
    负责管理所有与Unity交互相关的队列操作（动作映射、场景切换、机位切换等）
    """
    
    # 单例实例
    _instance = None
    
    @classmethod
    def get_instance(cls, max_size: int = 100):
        """
        获取单例实例
        
        参数:
            max_size: 队列最大长度
            
        返回:
            UnityQueueHandler单例实例
        """
        if cls._instance is None:
            cls._instance = cls(max_size)
        return cls._instance
    
    def __init__(self, max_size: int = 100):
        # 记录队列
        self.records = {
            "action": [],  # 动作映射记录
            "scene": [],   # 场景切换记录
            "camera": []   # 机位切换记录
        }
        self.queues = {
            "action": queue.Queue(),  # 动作映射队列
            "scene": queue.Queue(),   # 场景切换队列
            "camera": queue.Queue()   # 机位切换队列
        }
        self.record_id_counter = 0  # 记录ID计数器
        self.max_size = max_size    # 队列最大长度
        self.lock = threading.Lock() # 线程锁
    
    def add_record(self, record_type: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        添加记录到指定类型的队列
        
        参数:
            record_type: 记录类型，可选 'action'(动作映射)、'scene'(场景)、'camera'(机位)
            data: 记录数据
            
        返回:
            添加的记录，添加失败则返回None
        """
        if record_type not in self.records:
            return None
            
        with self.lock:
            # 添加基础信息
            record = data.copy()
            record["id"] = self.record_id_counter
            record["timestamp"] = int(time.time())
            record["type"] = record_type
            
            # 递增ID计数器
            self.record_id_counter += 1
            
            # 添加到记录列表
            self.records[record_type].append(record)
            
            # 添加到队列
            self.queues[record_type].put(record)
            
            # 如果记录数超过最大值，删除最早的记录
            if len(self.records[record_type]) > self.max_size:
                self.records[record_type].pop(0)
                
            return record
    
    def add_action_mapping(self, action_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        添加动作映射记录
        
        参数:
            action_data: 动作映射数据
            
        返回:
            添加的记录，添加失败则返回None
        """
        return self.add_record("action", action_data)
    
    def add_scene_change(self, scene_name: str) -> Optional[Dict[str, Any]]:
        """
        添加场景切换记录
        
        参数:
            scene_name: 场景名称
            
        返回:
            添加的记录，添加失败则返回None
        """
        data = {"name": scene_name}
        return self.add_record("scene", data)
    
    def add_camera_change(self, camera_name: str) -> Optional[Dict[str, Any]]:
        """
        添加机位切换记录
        
        参数:
            camera_name: 机位名称
            
        返回:
            添加的记录，添加失败则返回None
        """
        data = {"name": camera_name}
        return self.add_record("camera", data)
    
    def get_records(self, record_type: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        获取记录
        
        参数:
            record_type: 记录类型，可选 'action'(动作映射)、'scene'(场景)、'camera'(机位)或None(全部)
            limit: 返回的记录数量限制，None表示返回全部
            
        返回:
            包含记录数据和总数的字典
        """
        with self.lock:
            if record_type in self.records:
                filtered_records = self.records[record_type].copy()
            elif record_type is None:
                # 合并所有类型的记录
                filtered_records = []
                for records in self.records.values():
                    filtered_records.extend(records)
            else:
                return {"data": [], "count": 0, "queue_count": 0}
            
            # 获取队列中的记录（尚未处理的）
            queue_items = []
            if record_type in self.queues:
                temp_queue = queue.Queue()
                
                try:
                    while not self.queues[record_type].empty():
                        item = self.queues[record_type].get(block=False)
                        queue_items.append(item)
                        temp_queue.put(item)
                except queue.Empty:
                    pass
                
                # 将临时队列中的记录放回原队列
                while not temp_queue.empty():
                    try:
                        self.queues[record_type].put(temp_queue.get(block=False))
                    except queue.Empty:
                        break
            
            # 按时间倒序排序
            filtered_records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            # 限制返回数量
            if limit and limit > 0:
                filtered_records = filtered_records[:limit]
            
            # 格式化时间
            for record in filtered_records:
                if "timestamp" in record:
                    record["formatted_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record["timestamp"]))
            
            return {
                "data": filtered_records,
                "count": len(filtered_records),
                "queue_count": len(queue_items)
            }
    
    def get_action_mapping_queue(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        获取动作映射记录
        
        参数:
            limit: 返回的记录数量限制，None表示返回全部
            
        返回:
            包含记录数据和总数的字典
        """
        return self.get_records("action", limit)
    
    def get_scene_camera_changes(self, change_type: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        获取场景/机位切换记录
        
        参数:
            change_type: 变更类型，可选 'scene'(场景)、'camera'(机位)或None(全部)
            limit: 返回的记录数量限制，None表示返回全部
            
        返回:
            包含记录数据和总数的字典
        """
        if change_type in ["scene", "camera"]:
            return self.get_records(change_type, limit)
        else:
            # 合并场景和机位记录
            scene_records = self.get_records("scene", limit)
            camera_records = self.get_records("camera", limit)
            
            combined_records = scene_records["data"] + camera_records["data"]
            combined_records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
            if limit and limit > 0:
                combined_records = combined_records[:limit]
            
            return {
                "data": combined_records,
                "count": len(combined_records),
                "queue_count": scene_records["queue_count"] + camera_records["queue_count"]
            }
    
    def delete_record(self, record_type: str, record_id: Optional[int] = None, delete_all: bool = False) -> bool:
        """
        删除记录
        
        参数:
            record_type: 记录类型，可选 'action'(动作映射)、'scene'(场景)、'camera'(机位)
            record_id: 要删除的记录ID，None表示不按ID删除
            delete_all: 是否删除所有记录
            
        返回:
            是否成功删除
        """
        if record_type not in self.records:
            return False
            
        with self.lock:
            if delete_all:
                # 清空队列
                while not self.queues[record_type].empty():
                    try:
                        self.queues[record_type].get(block=False)
                    except queue.Empty:
                        break
                
                # 清空记录列表
                self.records[record_type] = []
                return True
            
            elif record_id is not None:
                # 按ID删除
                original_length = len(self.records[record_type])
                self.records[record_type] = [r for r in self.records[record_type] if r.get("id") != record_id]
                
                # 检查是否有记录被删除
                if len(self.records[record_type]) < original_length:
                    # 重建队列，移除被删除的记录
                    new_queue = queue.Queue()
                    temp_items = []
                    
                    try:
                        while not self.queues[record_type].empty():
                            item = self.queues[record_type].get(block=False)
                            if item.get("id") != record_id:
                                temp_items.append(item)
                    except queue.Empty:
                        pass
                    
                    for item in temp_items:
                        new_queue.put(item)
                    
                    self.queues[record_type] = new_queue
                    return True
                
                return False
            
            return False
    
    def delete_action_mapping(self, action_id: Optional[int] = None, delete_all: bool = False) -> bool:
        """
        删除动作映射记录
        
        参数:
            action_id: 要删除的动作ID，None表示不按ID删除
            delete_all: 是否删除所有记录
            
        返回:
            是否成功删除
        """
        return self.delete_record("action", action_id, delete_all)
    
    def delete_scene_camera_change(self, change_id: Optional[int] = None, change_type: Optional[str] = None, delete_all: bool = False) -> bool:
        """
        删除场景/机位切换记录
        
        参数:
            change_id: 要删除的记录ID，None表示不按ID删除
            change_type: 变更类型，可选 'scene'(场景)、'camera'(机位)或None(全部)
            delete_all: 是否删除所有记录
            
        返回:
            是否成功删除
        """
        if change_type in ["scene", "camera"]:
            return self.delete_record(change_type, change_id, delete_all)
        elif change_type is None and delete_all:
            # 删除所有场景和机位记录
            result1 = self.delete_record("scene", None, True)
            result2 = self.delete_record("camera", None, True)
            return result1 and result2
        elif change_id is not None:
            # 尝试在场景和机位记录中查找并删除指定ID的记录
            result1 = self.delete_record("scene", change_id, False)
            result2 = self.delete_record("camera", change_id, False)
            return result1 or result2
        
        return False
    
    def get_next_record(self, record_type: str) -> Optional[Dict[str, Any]]:
        """
        获取下一个记录
        
        参数:
            record_type: 记录类型，可选 'action'(动作映射)、'scene'(场景)、'camera'(机位)
            
        返回:
            下一个记录，如果队列为空则返回None
        """
        if record_type not in self.queues:
            return None
            
        try:
            return self.queues[record_type].get(block=False)
        except queue.Empty:
            return None
    
    def get_next_action_mapping(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个动作映射记录
        
        返回:
            下一个动作映射记录，如果队列为空则返回None
        """
        return self.get_next_record("action")
    
    def get_next_scene_change(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个场景切换记录
        
        返回:
            下一个场景切换记录，如果队列为空则返回None
        """
        return self.get_next_record("scene")
    
    def get_next_camera_change(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个机位切换记录
        
        返回:
            下一个机位切换记录，如果队列为空则返回None
        """
        return self.get_next_record("camera")
    
    def get_next_scene_camera_change(self) -> Optional[Dict[str, Any]]:
        """
        获取下一个场景或机位切换记录（先检查场景，再检查机位）
        
        返回:
            下一个场景或机位切换记录，如果队列为空则返回None
        """
        # 先检查是否有场景变更
        result = self.get_next_scene_change()
        if result:
            return result
        
        # 再检查是否有机位变更
        return self.get_next_camera_change()

# 创建全局单例实例
unity_queue_handler = UnityQueueHandler.get_instance() 