import io, sys
LOG = r'c:\Users\İzzet\Documents\trae_projects\course_register\_sanity.txt'
with io.open(LOG, 'w', encoding='utf-8') as g:
    g.write(u'Hello from Python\n')
    g.write(u'argv: ' + repr(sys.argv) + u'\n')
    g.write(u'python exe: ' + sys.executable + u'\n')
print('OK')
sys.exit(0)
