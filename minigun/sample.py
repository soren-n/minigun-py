# External module dependencies
from returns.maybe import Maybe, Nothing, Some

# Internal module dependencies
from minigun import arbitrary as a
from minigun import generate as g
from minigun import stream as fs


def slice[T](
    generator: g.Generator[T], max_width: int, max_depth: int, state: a.State
) -> tuple[a.State, Maybe[list[T]]]:
    """Sample a domain slice over a type `T`, outputting a list of values of type `T`, where the first value is randomly sampled from the given generator over `T`, and the following values in the list being a random path down through the shrink tree of that initially sampled value.

    :param generator: A generator over the type `T`.
    :type generator: `minigun.generate.Generator[T]`
    :param max_width: The max width with which to sample within the shrink tree.
    :type max_width: `int`
    :param max_depth: The max depth with which to sample within the shrink tree.
    :type max_depth: `int`
    :param state: The RNG state to sample with.
    :type state: `minigun.arbitrary.State`

    :return: A tuple with the next RNG state and the potentially sampled domain slice.
    :rtype: `tuple[minigun.arbitrary.State, returns.maybe.Maybe[list[T]]]`
    """
    sampler, _ = generator
    state, maybe_dissection = sampler(state)
    match maybe_dissection:
        case Maybe.empty:
            return state, Nothing
        case Some(dissection):
            items: list[T] = []
            for _ in range(max_depth):
                item, dissection_stream = dissection
                items.append(item)
                dissections = fs.to_list(dissection_stream, max_width)
                if len(dissections) == 0:
                    break
                state, dissection = a.choice(state, dissections)
            return state, Some(items)
        case _:
            raise AssertionError("Invariant")
