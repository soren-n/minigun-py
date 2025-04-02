from .negative import test as negative_test
from .positive import test as positive_test

def test():
    success = True
    success &= negative_test()
    success &= positive_test()
    return success

if __name__ == '__main__':
    import sys
    success = test()
    sys.exit(0 if success else -1)