"""
Unit tests cho SemanticValidator

Test cases cho semantic/logical validation.
"""

import pytest
from pathlib import Path
from validation_agent.core.semantic_validator import SemanticValidator


@pytest.fixture
def validator():
    """Fixture để tạo SemanticValidator instance"""
    return SemanticValidator()


@pytest.fixture
def valid_semantic_xosc(tmp_path):
    """Fixture tạo semantically valid .xosc file"""
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
    <ScenarioObject name="tv">
      <Vehicle name="vehicle.audi.tt" vehicleCategory="car">
        <Performance maxSpeed="50" maxAcceleration="3" maxDeceleration="8"/>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init>
      <Actions>
        <Private entityRef="ev">
          <PrivateAction>
            <TeleportAction>
              <Position>
                <LanePosition roadId="3" laneId="-2" s="0" offset="0"/>
              </Position>
            </TeleportAction>
          </PrivateAction>
        </Private>
        <Private entityRef="tv">
          <PrivateAction>
            <TeleportAction>
              <Position>
                <LanePosition roadId="3" laneId="-1" s="40" offset="0"/>
              </Position>
            </TeleportAction>
          </PrivateAction>
        </Private>
      </Actions>
    </Init>
    <Story name="story">
      <Act name="act">
        <ManeuverGroup name="mg" maximumExecutionCount="1">
          <Actors selectTriggeringEntities="false">
            <EntityRef entityRef="tv"/>
          </Actors>
          <Maneuver name="maneuver">
            <Event name="event1" priority="overwrite">
              <Action name="action">
                <PrivateAction>
                  <LateralAction>
                    <LaneChangeAction>
                      <LaneChangeActionDynamics dynamicsShape="sinusoidal" value="3" dynamicsDimension="time"/>
                      <LaneChangeTarget>
                        <RelativeTargetLane value="-1"/>
                      </LaneChangeTarget>
                    </LaneChangeAction>
                  </LateralAction>
                </PrivateAction>
              </Action>
              <StartTrigger>
                <ConditionGroup>
                  <Condition name="start1" delay="0" conditionEdge="rising">
                    <ByValueCondition>
                      <SimulationTimeCondition value="5" rule="greaterThan"/>
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
    <StopTrigger>
      <ConditionGroup>
        <Condition name="end" delay="0" conditionEdge="rising">
          <ByValueCondition>
            <SimulationTimeCondition value="20" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""
    file_path = tmp_path / "valid_semantic.xosc"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


class TestSemanticValidator:
    """Test suite cho SemanticValidator"""
    
    def test_valid_semantic_scenario(self, validator, valid_semantic_xosc):
        """Test validation với semantically valid scenario"""
        result = validator.validate(valid_semantic_xosc)
        
        assert result['valid'] == True
        assert len(result.get('errors', [])) == 0
    
    def test_invalid_actor_reference(self, validator, tmp_path):
        """Test detection của invalid actor references"""
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
    <Init>
      <Actions>
        <Private entityRef="nonexistent_actor">
          <PrivateAction>
            <TeleportAction>
              <Position>
                <LanePosition roadId="3" laneId="-2" s="0" offset="0"/>
              </Position>
            </TeleportAction>
          </PrivateAction>
        </Private>
      </Actions>
    </Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "invalid_actor_ref.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should detect invalid actor reference
        assert len(result.get('errors', [])) > 0
        errors_text = ' '.join(result['errors'])
        assert 'actor' in errors_text.lower() or 'entity' in errors_text.lower()
    
    def test_timeline_conflicts(self, validator, tmp_path):
        """Test detection của conflicting timeline events"""
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
            <Event name="event1" priority="overwrite">
              <Action name="action1">
                <PrivateAction>
                  <LongitudinalAction>
                    <SpeedAction>
                      <SpeedActionDynamics dynamicsShape="step" value="0" dynamicsDimension="time"/>
                      <SpeedActionTarget>
                        <AbsoluteTargetSpeed value="10"/>
                      </SpeedActionTarget>
                    </SpeedAction>
                  </LongitudinalAction>
                </PrivateAction>
              </Action>
              <StartTrigger>
                <ConditionGroup>
                  <Condition name="start1" delay="0" conditionEdge="rising">
                    <ByValueCondition>
                      <SimulationTimeCondition value="5" rule="greaterThan"/>
                    </ByValueCondition>
                  </Condition>
                </ConditionGroup>
              </StartTrigger>
            </Event>
            <Event name="event2" priority="overwrite">
              <Action name="action2">
                <PrivateAction>
                  <LongitudinalAction>
                    <SpeedAction>
                      <SpeedActionDynamics dynamicsShape="step" value="0" dynamicsDimension="time"/>
                      <SpeedActionTarget>
                        <AbsoluteTargetSpeed value="20"/>
                      </SpeedActionTarget>
                    </SpeedAction>
                  </LongitudinalAction>
                </PrivateAction>
              </Action>
              <StartTrigger>
                <ConditionGroup>
                  <Condition name="start2" delay="0" conditionEdge="rising">
                    <ByValueCondition>
                      <SimulationTimeCondition value="5.1" rule="greaterThan"/>
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
    <StopTrigger>
      <ConditionGroup>
        <Condition name="end" delay="0" conditionEdge="rising">
          <ByValueCondition>
            <SimulationTimeCondition value="20" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "timeline_conflict.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should warn about events too close in time
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0
    
    def test_stop_trigger_before_events(self, validator, tmp_path):
        """Test detection của StopTrigger trước khi events kết thúc"""
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
            <Event name="event1" priority="overwrite">
              <Action name="action1">
                <PrivateAction>
                  <LateralAction>
                    <LaneChangeAction>
                      <LaneChangeActionDynamics dynamicsShape="sinusoidal" value="5" dynamicsDimension="time"/>
                      <LaneChangeTarget>
                        <RelativeTargetLane value="1"/>
                      </LaneChangeTarget>
                    </LaneChangeAction>
                  </LateralAction>
                </PrivateAction>
              </Action>
              <StartTrigger>
                <ConditionGroup>
                  <Condition name="start1" delay="0" conditionEdge="rising">
                    <ByValueCondition>
                      <SimulationTimeCondition value="10" rule="greaterThan"/>
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
    <StopTrigger>
      <ConditionGroup>
        <Condition name="end" delay="0" conditionEdge="rising">
          <ByValueCondition>
            <SimulationTimeCondition value="12" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "early_stop.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should warn về StopTrigger possibly cutting off events
        # Event starts at 10s, duration 5s, ends at 15s, but stop at 12s
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])