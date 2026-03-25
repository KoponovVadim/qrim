from aiogram.fsm.state import State, StatesGroup


class AddPackStates(StatesGroup):
    waiting_for_name = State()
