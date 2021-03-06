#!/usr/bin/env python
# author:  Hua Liang [ Stupid ET ]
# email:   et@everet.org
# website: http://EverET.org
#
# database migrate from syntaxhighlighter evolved to wp-syntax

import re, sys

def sub(pat, text, new_str):
    py = re.compile(pat, re.IGNORECASE) 
    sql = py.sub(new_str, text) 
    return sql 

sql = sys.stdin.read() 
#sql = open('et.sql').read()

# [python] => <pre lang="python">
sql = sub(r'\[python.*?\]', sql, '<pre lang="python" escaped="true">')
sql = sub(r'\[/python\]', sql, '</pre>')

sql = sub(r'\[plain.*?\]', sql, '<pre lang="text" escaped="true">')
sql = sub(r'\[/plain\]', sql, '</pre>')

sql = sub(r'\[code.*?\]', sql, '<pre lang="text" escaped="true">')
sql = sub(r'\[/code\]', sql, '</pre>')

sql = sub(r'(\[c(\s.*?)?\])', sql, '<pre lang="cpp" escaped="true">')
sql = sub(r'\[/c\]', sql, '</pre>')

sql = sub(r'\[shell.*?\]', sql, '<pre lang="bash" escaped="true">')
sql = sub(r'\[/shell\]', sql, '</pre>')

sql = sub(r'\[php.*?\]', sql, '<pre lang="php" escaped="true">')
sql = sub(r'\[/php\]', sql, '</pre>')

sql = sub(r'\[lisp.*?\]', sql, '<pre lang="lisp" escaped="true">')
sql = sub(r'\[/lisp\]', sql, '</pre>')

sql = sub(r'\[javascript.*?\]', sql, '<pre lang="javascript" escaped="true">')
sql = sub(r'\[/javascript\]', sql, '</pre>')

sql = sub(r'\[html.*?\]', sql, '<pre lang="html" escaped="true">')
sql = sub(r'\[/html\]', sql, '</pre>')

sql = sub(r'\[c\+\+.*?\]', sql, '<pre lang="cpp" escaped="true">')
sql = sub(r'\[/c\+\+\]', sql, '</pre>')

sql = sub(r'\[c#.*?\]', sql, '<pre lang="csharp" escaped="true">')
sql = sub(r'\[/c#\]', sql, '</pre>')

# for s in re.findall(r'\<pre lang=\".*?\"\>', sql):
#     print s 
# for s in re.findall(r'\[/.*?\]', sql):
#     print s

#output = open('fix-et.sql', 'w')
output = sys.stdout
output.write(sql)
output.close()
