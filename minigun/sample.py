# External module dependencies
from typing import TypeVar

# Internal module dependencies
from . import arbitrary as a
from . import generate as g
from . import stream as fs

T = TypeVar('T')

def slice(
    generator: g.Generator[T],
    max_width: int,
    max_depth: int,
    state: a.State
    ) -> tuple[a.State, list[T]]:
    """Sample a domain slice over a type `T`, outputting a list of values of type `T`, where the first value is randomly sampled from the given generator over `T`, and the following values in the list being a random path down through the shrink tree of that initially sampled value.

    :param generator: A generator over the type `T`.
    :type generator: `minigun.generate.Generator[T]`
    :param max_width: The max width with which to sample within the shrink tree.
    :type max_width: `int`
    :param max_depth: The max depth with which to sample within the shrink tree.
    :type max_depth: `int`
    :param state: The RNG state to sample with.
    :type state: `minigun.arbitrary.State`

    :return: A tuple with the next RNG state and the sampled domain slice.
    :rtype: `Tuple[minigun.arbitrary.State, List[T]]`
    """
    state, dissection = generator(state)
    items: list[T] = []
    for _ in range(max_depth):
        item, dissection_stream = dissection
        items.append(item)
        dissections = fs.to_list(dissection_stream, max_width)
        if len(dissections) == 0: break
        state, dissection = a.choice(state, dissections)
    return state, items