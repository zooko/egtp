import string
import MojoErrors
from copy import copy

_MAX_VERNUM_LENGTH = 40  # max length in chars of a VersionNumber string

class VersionNumberParseError(MojoErrors.DataError):
    pass

class VersionNumber:
    def __init__(self, s):
        if len(s) > _MAX_VERNUM_LENGTH:
            raise ValueError, "string too long: "+s
        ints = []
        for i in string.split(s, '.'):
            try:
                ints.append(int(i))
                if i[0] == '-':
                    raise VersionNumberParseError, 'negatives not allowed'
            except ValueError, e:
                raise VersionNumberParseError, str(e)
        while(len(ints) > 0 and ints[-1] == 0):
            ints = ints[:-1]
        self.ints = ints
    
    def __cmp__(self, other):
        if not isinstance(other, VersionNumber):
            return -1
        for i in range(len(self.ints)):
            if len(other.ints) == i:
                return 1
            c = cmp(self.ints[i], other.ints[i])
            if c != 0:
                return c
        return cmp(len(self.ints), len(other.ints))

    def __str__(self):
        if len(self.ints) == 0:
            return '0'
        s = str(self.ints[0])
        for i in self.ints[1:]:
            s = s + '.' + str(i)
        return s

    def __repr__(self):
        return 'VersionNumber(\'' + str(self) + '\')'

def test_repr():
    def t(s):
        v = VersionNumber(s)
        assert eval(`v`) == v
    t('0')
    t('0.0')
    t('0.0.1')
    t('1.2.3')
    t('1')

def test_str():
    def t(s):
        v = VersionNumber(s)
        assert VersionNumber(str(v)) == v
    t('0')
    t('0.0')
    t('0.0.1')
    t('1.2.3')
    t('1')

def test_errors():
    def t(s):
        try:
            VersionNumber(s)
        except VersionNumberParseError:
            pass
        else:
            assert 0
    t('')
    t('.')
    t('a')
    t('0.')
    t('.1')
    t('-0')
    t('-1')

def test_not_equal():
    def t(s1, s2):
        a = VersionNumber(s1)
        b = VersionNumber(s2)
        assert a < b
        assert b > a
        assert a != b
        assert b != a
        assert not b <= a
        assert not a >= b
        assert not a == b
    t('0', '1')
    t('1', '2')
    t('1.1.2', '1.1.3')
    t('1.1', '1.1.2')
    t('1.2.2', '1.3.1')
    t('1', '1.0.2')
    t('1.0', '1.1.1')
    t('1.0', '1.0.1')

def test_equal():
    def t2(s1, s2):
        a = VersionNumber(s1)
        b = VersionNumber(s2)
        assert not a < b
        assert not b > a
        assert not a != b
        assert not b != a
        assert b <= a
        assert a >= b
        assert a == b
    def t(s, t2 = t2):
        t2(s, s)
    t('1')
    t('2.3')
    t('0')
    t('1.0.4')
    t2('1', '1.0')
    t2('1.0', '1.0.0')
    t2('1', '1.0.0')
    t2('0', '0.0')
