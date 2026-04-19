#!/usr/bin/env python3
"""
Demo script showing the configuration functionality with both URL formats
"""

import os
import tempfile
from argoproxy._vendor import yaml
import sys

# Add src directory to Python path
sys.path.insert(0, 'src')

from argoproxy.config import ArgoConfig, load_config, save_config

def demo_individual_urls():
    """Demo using individual URL configuration"""
    
    print("🔄 Configuration Demo: Individual URLs")
    print("=" * 50)
    
    # Create configuration with individual URLs
    individual_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "demo_user",
        "argo_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/",
        "argo_stream_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/",
        "argo_embedding_url": "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/",
        "verbose": True
    }
    
    print("\n📄 Individual URLs Configuration:")
    print(yaml.dump(individual_config, default_flow_style=False))
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(individual_config, f)
        temp_path = f.name
    
    try:
        print("🔍 Loading individual URLs configuration...")
        
        # Load the configuration
        config_data, _ = load_config(temp_path)
        
        if config_data:
            print("✅ Configuration loaded successfully!")
            print(f"   Uses base URL: {config_data.uses_base_url}")
            print(f"   Extracted base URL: {config_data.argo_base_url}")
            
            print("\n🔗 URL Configuration:")
            print(f"   Chat URL: {config_data.argo_url}")
            print(f"   Stream URL: {config_data.argo_stream_url}")
            print(f"   Embedding URL: {config_data.argo_embedding_url}")
            print(f"   Model URL: {config_data.argo_model_url}")
            
            print("\n🎯 Features:")
            print("   ✅ Traditional configuration method")
            print("   ✅ Full control over individual URLs")
            print("   ✅ Base URL automatically extracted for convenience")
            print("   ✅ Backward compatible")
            
        else:
            print("❌ Failed to load configuration")
            
    finally:
        # Clean up
        os.unlink(temp_path)

def demo_base_url():
    """Demo using base URL configuration"""
    
    print("\n" + "=" * 50)
    print("📄 Configuration Demo: Base URL")
    print("=" * 50)
    
    # Create base URL configuration
    base_url_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "demo_user",
        "argo_base_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/",
        "verbose": True
    }
    
    print("\n📄 Base URL Configuration:")
    print(yaml.dump(base_url_config, default_flow_style=False))
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(base_url_config, f)
        temp_path = f.name
    
    try:
        print("🔍 Loading base URL configuration...")
        
        # Load the configuration
        config_data, _ = load_config(temp_path)
        
        if config_data:
            print("✅ Configuration loaded successfully!")
            print(f"   Uses base URL: {config_data.uses_base_url}")
            print(f"   Base URL: {config_data.argo_base_url}")
            
            print("\n🔗 Automatically Constructed URLs:")
            print(f"   Chat URL: {config_data.argo_url}")
            print(f"   Stream URL: {config_data.argo_stream_url}")
            print(f"   Embedding URL: {config_data.argo_embedding_url}")
            print(f"   Model URL: {config_data.argo_model_url}")
            
            print("\n🎯 Benefits:")
            print("   ✅ Single source of truth for base URL")
            print("   ✅ Easier to change environments")
            print("   ✅ Reduced configuration complexity")
            print("   ✅ Automatic URL construction")
            
        else:
            print("❌ Failed to load configuration")
            
    finally:
        # Clean up
        os.unlink(temp_path)

def demo_mixed_config():
    """Demo showing base URL takes precedence over individual URLs"""
    
    print("\n" + "=" * 50)
    print("📄 Configuration Demo: Mixed (Base URL Priority)")
    print("=" * 50)
    
    # Create mixed configuration
    mixed_config = {
        "host": "0.0.0.0",
        "port": 44497,
        "user": "demo_user",
        "argo_url": "https://old-server.com/api/v1/resource/chat/",
        "argo_stream_url": "https://old-server.com/api/v1/resource/streamchat/",
        "argo_embedding_url": "https://old-server.com/api/v1/resource/embed/",
        "argo_base_url": "https://new-server.com/api/v1/",
        "verbose": True
    }
    
    print("\n📄 Mixed Configuration (base URL should take precedence):")
    print(yaml.dump(mixed_config, default_flow_style=False))
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(mixed_config, f)
        temp_path = f.name
    
    try:
        print("🔍 Loading mixed configuration...")
        
        # Load the configuration
        config_data, _ = load_config(temp_path)
        
        if config_data:
            print("✅ Configuration loaded successfully!")
            print(f"   Uses base URL: {config_data.uses_base_url}")
            print(f"   Base URL: {config_data.argo_base_url}")
            
            print("\n🔗 Final URLs (constructed from base URL):")
            print(f"   Chat URL: {config_data.argo_url}")
            print(f"   Stream URL: {config_data.argo_stream_url}")
            print(f"   Embedding URL: {config_data.argo_embedding_url}")
            print(f"   Model URL: {config_data.argo_model_url}")
            
            if "new-server.com" in config_data.argo_url:
                print("\n✅ Base URL correctly takes precedence over individual URLs")
            else:
                print("\n❌ Individual URLs incorrectly used instead of base URL")
            
        else:
            print("❌ Failed to load configuration")
            
    finally:
        # Clean up
        os.unlink(temp_path)

if __name__ == "__main__":
    demo_individual_urls()
    demo_base_url()
    demo_mixed_config()
    
    print("\n" + "=" * 50)
    print("🎉 Configuration Demo Complete!")
    print("=" * 50)
    print("\nThe configuration system now supports:")
    print("• Individual URL configuration (traditional)")
    print("• Base URL configuration (simplified)")
    print("• Mixed configuration (base URL takes precedence)")
    print("• Automatic URL construction")
    print("• Full backward compatibility")