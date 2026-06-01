@echo off
chcp 65001
setlocal

:: ================= 配置区 =================
set "PYTHON_SCRIPT=%~dp0llm_score_evaluator.py"
set "DEFAULT_INPUT=%~dp0Excel_Data\KB1知识库-0206.xlsx"
set "OUTPUT_DIR=%~dp0Output"

:: 查找 Python
if exist "..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\.venv\Scripts\python.exe"
) else (
    if exist ".venv\Scripts\python.exe" (
        set "PYTHON_EXE=.venv\Scripts\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
)
:: =========================================

echo.
echo ========================================================
echo       KB1 知识库 LLM 自动评分工具 (集成版)
echo ========================================================
echo.
echo  当前脚本已集成：
echo  1. V7 Prompt (含最新关键词堆砌扣分规则)
echo  2. 官方产品型号库 (自动识别扫地机/洗地机等)
echo  3. 多媒体加分逻辑 (图/视频+3分)
echo  4. 自动断点续传与 API 速率保护
echo.
echo ========================================================
echo.

:MENU
echo 请选择运行模式:
echo.
echo [1] 快速验证 (随机抽样 50 条)
echo [2] 全量运行 (处理所有数据)
echo [3] 自定义输入文件路径 (处理其他 Excel)
echo [Q] 退出
echo.

set /p choice=请输入选项 (1/2/3/Q): 

if /i "%choice%"=="1" goto RUN_SAMPLE
if /i "%choice%"=="2" goto RUN_FULL
if /i "%choice%"=="3" goto RUN_CUSTOM
if /i "%choice%"=="Q" goto END

echo 无效选项，请重新输入。
goto MENU

:RUN_SAMPLE
echo.
echo 正在启动 50 条抽样测试...
"%PYTHON_EXE%" "%PYTHON_SCRIPT%" --input "%DEFAULT_INPUT%" --limit 50 --output_dir "%OUTPUT_DIR%"
pause
goto MENU

:RUN_FULL
echo.
echo ⚠️  注意：全量运行可能耗时较长，支持断点续传。
echo 正在启动全量评分...
"%PYTHON_EXE%" "%PYTHON_SCRIPT%" --input "%DEFAULT_INPUT%" --limit 0 --output_dir "%OUTPUT_DIR%"
pause
goto MENU

:RUN_CUSTOM
echo.
set /p custom_input=请拖入或粘贴 Excel 文件路径: 
:: 去除引号
set custom_input=%custom_input:"=%

if not exist "%custom_input%" (
    echo.
    echo ❌ 错误：文件不存在！
    pause
    goto MENU
)

echo.
echo [1] 抽样 50 条
echo [2] 全量运行
set /p sub_choice=请选择模式 (1/2): 

if "%sub_choice%"=="1" (
    "%PYTHON_EXE%" "%PYTHON_SCRIPT%" --input "%custom_input%" --limit 50 --output_dir "%OUTPUT_DIR%"
) else (
    "%PYTHON_EXE%" "%PYTHON_SCRIPT%" --input "%custom_input%" --limit 0 --output_dir "%OUTPUT_DIR%"
)
pause
goto MENU

:END
endlocal
exit
