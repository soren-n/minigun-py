from minigun.specify import prop, check

@prop('fails')
def _fails(xs : list[int], ys : list[int]):
    return (
        list(reversed(xs + ys)) ==
        list(reversed(xs)) + list(reversed(ys))
    )

if __name__ == '__main__':
    import sys
    success = check(_fails)
    sys.exit(0 if success else -1)