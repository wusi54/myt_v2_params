# 风控优化点优先级（OPPO A3x 5G 为基准）

## P0（立即）
1. 补齐并轮换 wifi MAC / bt MAC / android_id / serialno
2. 基带两段版本号一致（不强行替换为 MOLY）
3. 打散设备级强关联字段

## P1（短期）
4. OAID 洗白与格式校验
5. 填充 sensors
6. 基站信息填充与地理一致性
7. RADIO_VERSION 纳入轮换

## P2（中期）
8. 保留分区时间戳差值，整体微扰
9. MAC OUI 归属确认
10. ro.baseband 取值确认
11. deviceId 格式确认

## P3（长期）
12. 设备间微差异
13. 基站数据真实性
14. 严格模式默认开启
