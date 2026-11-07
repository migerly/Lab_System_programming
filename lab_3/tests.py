"""Run: python3 tests.py. Compare AST execution with generated Python."""
import math
from pathlib import Path
import unittest
import compiler as c

class CompilerTests(unittest.TestCase):
    def value(self, body, expected):
        tree = c.parse('int main() {'+body+'}')
        c.check(tree)
        self.assertEqual(c.run(tree), expected)
        ns = {'__name__': 'test'}
        exec(c.generate(tree), ns)
        self.assertEqual(ns['main'](), expected)

    def test_precedence(self): self.value('return 2+3*4;', 14)
    def test_factorial(self):
        self.value('int n=5; int r=1; while(n>1){r=r*n;n=n-1;} return r;',120)
    def test_gcd(self):
        source = (Path(__file__).parent/'examples/gcd.c').read_text(encoding='utf-8')
        for a, b in ((48,18),(18,48),(17,13),(24,24),(0,9),(9,0),(0,0),(-48,18),(48,-18),(-48,-18)):
            with self.subTest(a=a, b=b):
                modified = source.replace('int a = 35;', f'int a = {a};').replace('int b = 64;', f'int b = {b};')
                tree = c.parse(modified)
                c.check(tree)
                expected = math.gcd(a,b)
                self.assertEqual(c.run(tree), expected)
                ns = {'__name__': 'test'}
                exec(c.generate(tree), ns)
                self.assertEqual(ns['main'](), expected)
    def test_division(self): self.value('return (-7/3)*10 + (-7%3);', -21)
    def test_short_circuit(self): self.value('return (0 && (1/0)) + (1 || (1/0));',1)
    def test_shadowing(self): self.value('int x=4; {int x=x+2;x=7;} return x;',4)
    def test_dangling_else(self): self.value('if(1) if(0) return 1; else return 2; return 3;',2)
    def test_empty(self): self.value('{}',0)
    def test_comments(self): self.value('/* a\nb */ int x=3; // hi\nreturn !x;',0)
    def test_bad_syntax(self):
        for src in ('int main(){int x=1 return x;}', 'int main(){return @;}', 'int main(){'):
            with self.assertRaises(SyntaxError): c.parse(src)
    def test_semantics(self):
        for body in ('return x;', 'int x; int x;', 'if(0){return missing;}', '{int x=1;} return x;', 'if(1) int x=2;'):
            with self.assertRaises(ValueError): c.check(c.parse('int main(){'+body+'}'))
    def test_zero_division(self):
        with self.assertRaises(ValueError): c.run(c.parse('int main(){return 1/0;}'))
    def test_loop_limit(self):
        with self.assertRaises(ValueError): c.run(c.parse('int main(){while(1){}}'),100)

if __name__ == '__main__': unittest.main(verbosity=2)
