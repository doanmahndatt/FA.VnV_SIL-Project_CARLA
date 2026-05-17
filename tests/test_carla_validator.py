
"""
Unit tests cho CarlaValidator

Test cases cho CARLA-specific validation.
"""

import pytest
from pathlib import Path
from validation_agent.core.carla_validator import CarlaValidator


@pytest.fixture
def validator():
    """Fixture để tạo CarlaValidator instance"""
    return CarlaValidator()


@pytest.fixture
def valid_carla_xosc(tmp_path):
    """Fixture tạo valid CARLA-compatible .xosc file"""
    content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="CARLA Test"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="ev">
      <Vehicle name="vehicle.tesla.model3" vehicleCategory="car">
        <Performance maxSpeed="50" maxAcceleration="3" maxDeceleration="8"/>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init>
      <Actions>
        <GlobalAction>
          <EnvironmentAction>
            <Environment name="env">
              <TimeOfDay animation="false" dateTime="2026-01-01T12:00:00"/>
              <Weather cloudState="free">
                <Sun intensity="1.0" azimuth="0" elevation="70"/>
                <Fog visualRange="100000"/>
                <Precipitation precipitationType="dry" intensity="0"/>
              </Weather>
            </Environment>
          </EnvironmentAction>
        </GlobalAction>
      </Actions>
    </Init>
  </Storyboard>
</OpenSCENARIO>
"""
    file_path = tmp_path / "valid_carla.xosc"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


class TestCarlaValidator:
    """Test suite cho CarlaValidator"""
    
    def test_valid_carla_scenario(self, validator, valid_carla_xosc):
        """Test validation với valid CARLA scenario"""
        result = validator.validate(valid_carla_xosc)
        
        assert result['valid'] == True
        assert len(result.get('errors', [])) == 0
    
    def test_invalid_map_name(self, validator, tmp_path):
        """Test detection của invalid CARLA map name"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test"/>
  <RoadNetwork>
    <LogicFile filepath="InvalidTown"/>
  </RoadNetwork>
  <Entities/>
  <Storyboard>
    <Init><Actions/></Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "invalid_map.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should detect invalid map
        assert len(result.get('errors', [])) > 0 or len(result.get('warnings', [])) > 0
        errors_warnings = ' '.join(result.get('errors', []) + result.get('warnings', []))
        assert 'map' in errors_warnings.lower() or 'town' in errors_warnings.lower()
    
    def test_invalid_vehicle_model(self, validator, tmp_path):
        """Test detection của invalid vehicle model"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="ev">
      <Vehicle name="vehicle.invalid.model" vehicleCategory="car">
        <Performance maxSpeed="50" maxAcceleration="3" maxDeceleration="8"/>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions/></Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "invalid_vehicle.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should warn about unknown vehicle model
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0
    
    def test_physics_limits_violation(self, validator, tmp_path):
        """Test detection của physics limits violations"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="ev">
      <Vehicle name="vehicle.tesla.model3" vehicleCategory="car">
        <Performance maxSpeed="150" maxAcceleration="20" maxDeceleration="30"/>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions/></Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "physics_violation.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should detect physics violations
        assert len(result.get('errors', [])) > 0 or len(result.get('warnings', [])) > 0
        messages = ' '.join(result.get('errors', []) + result.get('warnings', []))
        assert 'speed' in messages.lower() or 'acceleration' in messages.lower()
    
    def test_weather_limits(self, validator, tmp_path):
        """Test validation của weather parameters"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities/>
  <Storyboard>
    <Init>
      <Actions>
        <GlobalAction>
          <EnvironmentAction>
            <Environment name="env">
              <Weather cloudState="free">
                <Sun intensity="2.0" azimuth="0" elevation="70"/>
                <Fog visualRange="50"/>
                <Precipitation precipitationType="rain" intensity="150"/>
              </Weather>
            </Environment>
          </EnvironmentAction>
        </GlobalAction>
      </Actions>
    </Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "weather_test.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should warn about extreme weather values
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0
    
    def test_lane_change_duration(self, validator, tmp_path):
        """Test validation của lane change duration limits"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="ev">
      <Vehicle name="vehicle.tesla.model3" vehicleCategory="car">
        <Performance maxSpeed="50" maxAcceleration="3" maxDeceleration="8"/>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions/></Init>
    <Story name="story">
      <Act name="act">
        <ManeuverGroup name="mg" maximumExecutionCount="1">
          <Actors selectTriggeringEntities="false">
            <EntityRef entityRef="ev"/>
          </Actors>
          <Maneuver name="maneuver">
            <Event name="event" priority="overwrite">
              <Action name="action">
                <PrivateAction>
                  <LateralAction>
                    <LaneChangeAction>
                      <LaneChangeActionDynamics dynamicsShape="sinusoidal" value="0.5" dynamicsDimension="time"/>
                      <LaneChangeTarget>
                        <RelativeTargetLane value="1"/>
                      </LaneChangeTarget>
                    </LaneChangeAction>
                  </LateralAction>
                </PrivateAction>
              </Action>
              <StartTrigger>
                <ConditionGroup>
                  <Condition name="start" delay="0" conditionEdge="rising">
                    <ByValueCondition>
                      <SimulationTimeCondition value="0" rule="greaterThan"/>
                    </ByValueCondition>
                  </Condition>
                </ConditionGroup>
              </StartTrigger>
            </Event>
          </Maneuver>
        </ManeuverGroup>
        <StartTrigger>
          <ConditionGroup>
            <Condition name="start" delay="0" conditionEdge="rising">
              <ByValueCondition>
                <SimulationTimeCondition value="0" rule="greaterThan"/>
              </ByValueCondition>
            </Condition>
          </ConditionGroup>
        </StartTrigger>
      </Act>
    </Story>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "lane_change_test.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should warn about too fast lane change
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])