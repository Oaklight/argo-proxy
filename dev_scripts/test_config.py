#!/usr/bin/env python3
"""
Test script for configuration functionality with both URL formats
"""

import os
import tempfile
from argoproxy._vendor import yaml
from pathlib import Path

# Add src directory to Python path
import sys
sys.path.insert(0, 'src')

from argoproxy.config import ArgoConfig, load_config, save_config

def test_individual_urls_config():
    """Test configuration using individual URL fields"""
    
    # Create configuration with individual URLs
    individual_urls_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "testuser",
        "argo_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/",
        "argo_stream_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/",
        "argo_embedding_url": "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/",
        "verbose": True
    }
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(individual_urls_config, f)
        temp_config_path = f.name
    
    try:
        print("=== Testing Individual URLs Configuration ===")
        print(f"Temporary config file: {temp_config_path}")
        
        # Load config
        config_data, actual_path = load_config(temp_config_path)
        
        if not config_data:
            print("❌ Config loading failed")
            return False
            
        print(f"✅ Config loaded successfully")
        print(f"Uses base URL: {config_data.uses_base_url}")
        print(f"argo_base_url: {config_data.argo_base_url}")
        print(f"argo_url: {config_data.argo_url}")
        print(f"argo_stream_url: {config_data.argo_stream_url}")
        print(f"argo_embedding_url: {config_data.argo_embedding_url}")
        
        # Verify base URL was extracted
        expected_base = "https://apps-dev.inside.anl.gov/argoapi/api/v1/"
        if config_data.argo_base_url == expected_base:
            print("✅ Base URL extracted correctly from individual URLs")
        else:
            print(f"❌ Base URL extraction failed: {config_data.argo_base_url}")
            return False
            
        # Verify URLs remain the same
        if config_data.argo_url == individual_urls_config["argo_url"]:
            print("✅ argo_url preserved correctly")
        else:
            print(f"❌ argo_url changed unexpectedly: {config_data.argo_url}")
            return False
            
        # Test saving config
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            new_config_path = f.name
            
        save_config(config_data, new_config_path)
        
        # Read saved config file
        with open(new_config_path, 'r') as f:
            saved_config = yaml.load(f.read())
            
        print(f"Saved config keys: {list(saved_config.keys())}")
        
        # Verify saved config contains all fields
        expected_fields = ["argo_url", "argo_stream_url", "argo_embedding_url", "argo_base_url"]
        has_all_fields = all(field in saved_config for field in expected_fields)
        
        if has_all_fields:
            print("✅ Saved config contains all URL fields")
        else:
            missing_fields = [field for field in expected_fields if field not in saved_config]
            print(f"❌ Saved config missing fields: {missing_fields}")
            return False
            
        # Clean up temporary files
        os.unlink(new_config_path)
        
        return True
        
    finally:
        # Clean up temporary files
        os.unlink(temp_config_path)

def test_base_url_config():
    """Test configuration using argo_base_url"""
    
    # Create configuration with base URL
    base_url_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "testuser",
        "argo_base_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/",
        "verbose": True
    }
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(base_url_config, f)
        temp_config_path = f.name
    
    try:
        print("\n=== Testing Base URL Configuration ===")
        print(f"Temporary config file: {temp_config_path}")
        
        # Load config
        config_data, actual_path = load_config(temp_config_path)
        
        if not config_data:
            print("❌ Config loading failed")
            return False
            
        print(f"✅ Config loaded successfully")
        print(f"Uses base URL: {config_data.uses_base_url}")
        print(f"argo_base_url: {config_data.argo_base_url}")
        print(f"argo_url: {config_data.argo_url}")
        print(f"argo_stream_url: {config_data.argo_stream_url}")
        print(f"argo_embedding_url: {config_data.argo_embedding_url}")
        
        # Verify uses base URL
        if config_data.uses_base_url:
            print("✅ Configuration uses base URL")
        else:
            print("❌ Configuration should use base URL")
            return False
            
        # Verify URL construction is correct
        expected_urls = {
            "argo_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/",
            "argo_stream_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/",
            "argo_embedding_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/embed/",
            "argo_model_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/models/"
        }
        
        for url_name, expected_url in expected_urls.items():
            actual_url = getattr(config_data, url_name)
            if actual_url == expected_url:
                print(f"✅ {url_name} constructed correctly")
            else:
                print(f"❌ {url_name} construction failed: {actual_url}")
                return False
                
        return True
        
    finally:
        # Clean up temporary files
        os.unlink(temp_config_path)

def test_mixed_config():
    """Test configuration with both base URL and individual URLs (base URL should take precedence)"""
    
    # Create configuration with both formats
    mixed_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "testuser",
        "argo_url": "https://old-server.com/api/v1/resource/chat/",
        "argo_stream_url": "https://old-server.com/api/v1/resource/streamchat/",
        "argo_embedding_url": "https://old-server.com/api/v1/resource/embed/",
        "argo_base_url": "https://new-server.com/api/v1/",
        "verbose": True
    }
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(mixed_config, f)
        temp_config_path = f.name
    
    try:
        print("\n=== Testing Mixed Configuration (base URL should take precedence) ===")
        print(f"Temporary config file: {temp_config_path}")
        
        # Load config
        config_data, actual_path = load_config(temp_config_path)
        
        if not config_data:
            print("❌ Config loading failed")
            return False
            
        print(f"✅ Config loaded successfully")
        print(f"Uses base URL: {config_data.uses_base_url}")
        print(f"argo_base_url: {config_data.argo_base_url}")
        print(f"argo_url: {config_data.argo_url}")
        
        # Verify base URL takes precedence
        if "new-server.com" in config_data.argo_url:
            print("✅ Base URL takes precedence over individual URLs")
        else:
            print(f"❌ Individual URLs incorrectly used: {config_data.argo_url}")
            return False
                
        return True
        
    finally:
        # Clean up temporary files
        os.unlink(temp_config_path)

if __name__ == "__main__":
    print("Starting configuration functionality tests...\n")
    
    success1 = test_individual_urls_config()
    success2 = test_base_url_config()
    success3 = test_mixed_config()
    
    print(f"\n=== Test Results ===")
    print(f"Individual URLs config test: {'✅ PASSED' if success1 else '❌ FAILED'}")
    print(f"Base URL config test: {'✅ PASSED' if success2 else '❌ FAILED'}")
    print(f"Mixed config test: {'✅ PASSED' if success3 else '❌ FAILED'}")
    
    if success1 and success2 and success3:
        print("\n🎉 All tests passed! Configuration functionality works correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed, please check the code.")
        sys.exit(1)