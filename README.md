# myt_v2_params - 设备指纹裂变项目

按 **机型 (brand/model)** + **机型模板 (template)** 组织，支持针对不同机型模板进行优化生成。

## 目录结构

```
myt_v2_params/
├── templates/          # 原始真机采集母本（按机型）
│   └── <brand>/<model>/<template>.dat
├── scripts/            # 生成脚本（按机型）
│   ├── <brand>/<model>.py
│   └── common/         # 通用工具函数
├── output/             # 生成结果（按机型/批次）
│   └── <brand>/<model>/<batch>/
├── tools/              # 校验与交叉验证工具
├── docs/               # 优化点与优先级文档
└── config/             # 机型-模板-脚本注册表
```

## 快速开始

```bash
# OPPO A3x 5G（带种子/批次/清单，可复现）
python scripts/oppo/a3x_v2.py -f templates/oppo/A3x_5G/OPPO_A3x_5G.dat \
  -o output/oppo/A3x_5G/batch_001/out -c 100 -s \
  --seed 42 --batch-id A --ip-region cn
```

## 校验

```bash
python tools/validate.py output/oppo/A3x_5G/batch_001/
python tools/cross_check.py output/oppo/A3x_5G/batch_001/
```

## Web 管理页面

```bash
# 启动
python web/app.py
# 或双击 web/run.bat
# 浏览器打开 http://127.0.0.1:5000
```

功能：机型/模板选择、生成参数配置、基站池选择、IP 地区一致性校验、任务日志、批次管理、validate/cross_check、文件预览。
