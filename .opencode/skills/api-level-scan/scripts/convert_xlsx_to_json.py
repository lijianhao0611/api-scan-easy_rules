#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import json
import sys

def convert_xlsx_to_json(xlsx_path, output_path=None):
    df = pd.read_excel(xlsx_path, sheet_name='评估模型（目标稿）', header=None)
    
    data = df.iloc[3:, [5, 6, 7, 8]].copy()
    data.columns = ['id', 'description', 'examples', 'instructions']
    
    rules = []
    for _, row in data.iterrows():
        if pd.isna(row['id']):
            continue
        if 'APITEST.ERRORCODE.04' in row['id']:
            continue
        
        record = {
            'id': str(row['id']).strip() if pd.notna(row['id']) else None,
            'description': str(row['description']).strip() if pd.notna(row['description']) else None,
            'examples': str(row['examples']).strip() if pd.notna(row['examples']) else None,
            'instructions': str(row['instructions']).strip() if pd.notna(row['instructions']) else None
        }
        rules.append(record)
    
    result = {'rules': rules}
    
    if output_path is None:
        output_path = xlsx_path.rsplit('.', 1)[0] + '.json'
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f'转换完成！共生成 {len(rules)} 条记录')
    print(f'输出文件: {output_path}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python convert_xlsx_to_json.py <xlsx文件路径> [输出json路径]')
        sys.exit(1)
    
    xlsx_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    convert_xlsx_to_json(xlsx_path, output_path)