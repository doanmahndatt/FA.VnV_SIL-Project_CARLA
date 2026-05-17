@echo off

echo ================================
echo Starting CARLA tools
echo ================================

set BASE=%~dp0

cd /d %BASE%


echo Starting camera...
start cmd /k python config\camera.py


echo Starting HUD...
start cmd /k python config\hud.py


echo Starting ACC controller...
start cmd /k python acc_controller.py


echo ================================
echo All tools started
echo ================================

pause
