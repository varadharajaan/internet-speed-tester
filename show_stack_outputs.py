#!/usr/bin/env python3
"""
Show SAM/CloudFormation stack outputs in a nicely formatted way.
Saves to stack-outputs.txt and prints to console.
"""

import boto3
import json
from datetime import datetime
import os

# Configuration
STACK_NAME = "vd-speedtest-stack"
REGION = "ap-south-1"
OUTPUT_FILE = "stack-outputs.txt"


def get_stack_outputs():
    """Fetch outputs from CloudFormation stack."""
    cf = boto3.client("cloudformation", region_name=REGION)
    
    try:
        response = cf.describe_stacks(StackName=STACK_NAME)
        stacks = response.get("Stacks", [])
        
        if not stacks:
            print(f"❌ Stack '{STACK_NAME}' not found")
            return None
            
        return stacks[0].get("Outputs", [])
    except Exception as e:
        print(f"❌ Error fetching stack: {e}")
        return None


def format_outputs(outputs):
    """Format outputs into a nice string."""
    line = "=" * 80
    
    content = f"""{line}
                    VD-SPEEDTEST STACK DEPLOYMENT OUTPUTS
{line}
Deployed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Stack:    {STACK_NAME}
Region:   {REGION}
{line}

"""
    
    # Sort by key name
    for output in sorted(outputs, key=lambda x: x.get("OutputKey", "")):
        key = output.get("OutputKey", "Unknown")
        desc = output.get("Description", "No description")
        value = output.get("OutputValue", "N/A")
        
        content += f"{key}\n  {desc}\n  {value}\n\n"
    
    content += line
    return content


def main():
    print(f"📦 Fetching outputs from stack: {STACK_NAME}...")
    
    outputs = get_stack_outputs()
    if not outputs:
        return
    
    formatted = format_outputs(outputs)
    
    # Save to file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, OUTPUT_FILE)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(formatted)
    
    print(f"✅ Saved to {OUTPUT_FILE}\n")
    print(formatted)


if __name__ == "__main__":
    main()
