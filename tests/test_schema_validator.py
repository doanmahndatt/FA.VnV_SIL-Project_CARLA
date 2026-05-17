"""
Unit tests cho SchemaValidator

Test cases cho ASAM OpenSCENARIO schema validation.
"""

import pytest
from pathlib import Path
from validation_agent.core.schema_validator import SchemaValidator


@pytest.fixture
def validator():
    """Fixture để tạo SchemaValidator instance"""
    return SchemaValidator()


@pytest.fixture
def valid_xosc_file(tmp_path):
    """Fixture tạo valid .xosc file"""
    content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0" date="2026-05-14T00:00:00" description="Test scenario" author="Test"/>
  <ParameterDeclarations/>
  <CatalogLocations/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities>
    <ScenarioObject name="ev">
      <Vehicle name="vehicle.tesla.model3" vehicleCategory="car">
        <Performance maxSpeed="50" maxAcceleration="3" maxDeceleration="8"/>
        <BoundingBox>
          <Center x="1.5" y="0" z="0.9"/>
          <Dimensions width="2.0" length="4.5" height="1.5"/>
        </BoundingBox>
        <Axles>
          <FrontAxle maxSteering="0.5" wheelDiameter="0.6" trackWidth="1.6" positionX="3.1" positionZ="0.3"/>
          <RearAxle maxSteering="0.0" wheelDiameter="0.6" trackWidth="1.6" positionX="0.0" positionZ="0.3"/>
        </Axles>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init>
      <Actions/>
    </Init>
    <Story name="main_story">
      <Act name="act_1">
        <ManeuverGroup name="group_1" maximumExecutionCount="1">
          <Actors selectTriggeringEntities="false">
            <EntityRef entityRef="ev"/>
          </Actors>
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
            <SimulationTimeCondition value="10" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""
    file_path = tmp_path / "valid_scenario.xosc"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


@pytest.fixture
def invalid_xosc_file(tmp_path):
    """Fixture tạo invalid .xosc file (missing FileHeader)"""
    content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <ParameterDeclarations/>
  <Entities/>
  <Storyboard>
    <Init>
      <Actions/>
    </Init>
  </Storyboard>
</OpenSCENARIO>
"""
    file_path = tmp_path / "invalid_scenario.xosc"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


@pytest.fixture
def malformed_xml_file(tmp_path):
    """Fixture tạo malformed XML file"""
    content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1" revMinor="0">
  <!-- Missing closing tag -->
</OpenSCENARIO>
"""
    file_path = tmp_path / "malformed.xosc"
    file_path.write_text(content, encoding='utf-8')
    return str(file_path)


class TestSchemaValidator:
    """Test suite cho SchemaValidator"""
    
    def test_valid_xosc_file(self, validator, valid_xosc_file):
        """Test validation với valid .xosc file"""
        result = validator.validate(valid_xosc_file)
        
        assert result['valid'] == True
        assert len(result.get('errors', [])) == 0
        assert 'message' in result
    
    def test_missing_required_elements(self, validator, invalid_xosc_file):
        """Test detection của missing required elements"""
        result = validator.validate(invalid_xosc_file)
        
        assert result['valid'] == False
        assert len(result.get('errors', [])) > 0
        
        # Should detect missing FileHeader
        errors_text = ' '.join(result['errors'])
        assert 'FileHeader' in errors_text
    
    def test_malformed_xml(self, validator, malformed_xml_file):
        """Test handling của malformed XML"""
        result = validator.validate(malformed_xml_file)
        
        assert result['valid'] == False
        assert len(result.get('errors', [])) > 0
        assert 'XML' in result['errors'][0] or 'parse' in result['errors'][0].lower()
    
    def test_missing_file_header_attributes(self, validator, tmp_path):
        """Test detection của missing FileHeader attributes"""
        content = """<?xml version='1.0' encoding='utf-8'?>
<OpenSCENARIO>
  <FileHeader revMajor="1"/>
  <RoadNetwork>
    <LogicFile filepath="Town03"/>
  </RoadNetwork>
  <Entities/>
  <Storyboard>
    <Init><Actions/></Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "missing_attrs.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should have warnings về missing attributes
        assert len(result.get('warnings', [])) > 0 or len(result.get('errors', [])) > 0
    
    def test_nonexistent_file(self, validator):
        """Test handling của nonexistent file"""
        result = validator.validate("nonexistent_file.xosc")
        
        assert result['valid'] == False
        assert len(result.get('errors', [])) > 0
    
    def test_element_hierarchy(self, validator, tmp_path):
        """Test validation của element hierarchy"""
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
            <SimulationTimeCondition value="10" rule="greaterThan"/>
          </ByValueCondition>
        </Condition>
      </ConditionGroup>
    </StopTrigger>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "hierarchy_test.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Should validate hierarchy correctly
        assert result['valid'] == True or len(result.get('errors', [])) == 0
    
    def test_vehicle_properties(self, validator, tmp_path):
        """Test validation của vehicle properties"""
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
        <BoundingBox>
          <Center x="1.5" y="0" z="0.9"/>
          <Dimensions width="2.0" length="4.5" height="1.5"/>
        </BoundingBox>
        <Axles>
          <FrontAxle maxSteering="0.5" wheelDiameter="0.6" trackWidth="1.6" positionX="3.1" positionZ="0.3"/>
          <RearAxle maxSteering="0.0" wheelDiameter="0.6" trackWidth="1.6" positionX="0.0" positionZ="0.3"/>
        </Axles>
      </Vehicle>
    </ScenarioObject>
  </Entities>
  <Storyboard>
    <Init><Actions/></Init>
  </Storyboard>
</OpenSCENARIO>
"""
        file_path = tmp_path / "vehicle_test.xosc"
        file_path.write_text(content, encoding='utf-8')
        
        result = validator.validate(str(file_path))
        
        # Vehicle should have all required properties
        assert result['valid'] == True or len(result.get('errors', [])) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])