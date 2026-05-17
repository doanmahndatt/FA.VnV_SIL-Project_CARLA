@echo off

echo ================================
echo Starting CARLA tools
echo ================================

set BASE=C:\OpenScenario\Test_assets_v1.0\tools

cd /d %BASE%


echo Starting camera...
start cmd /k py -3.7 camera.py


echo Starting HUD...
start cmd /k py -3.7 hud.py


echo Starting ACC controller...
start cmd /k py -3.7 acc_controller.py


echo ================================
echo All tools started
echo ================================

pause