"""複数機種プロファイルからの選択画面(カード形式)。"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.profile_loader import MachineProfile


def render_header_image(profile: MachineProfile) -> None:
    if profile.header_image and Path(profile.header_image).exists():
        st.image(profile.header_image, use_container_width=True)


def render_machine_picker(profiles: list[MachineProfile]) -> None:
    """機種をカードから選ばせ、選択結果をst.session_stateに保存する。
    選択後はst.rerun()で再描画されるので、この関数自体は値を返さない。
    """
    st.subheader("機種を選択")
    cols = st.columns(2)
    for i, profile in enumerate(profiles):
        with cols[i % 2]:
            with st.container(border=True):
                has_image = profile.header_image and Path(profile.header_image).exists()
                if has_image:
                    render_header_image(profile)
                else:
                    st.markdown(
                        "<div style='font-size:2.5rem;text-align:center;'>🎰</div>",
                        unsafe_allow_html=True,
                    )
                st.markdown(f"**{profile.name}**")
                if st.button("選ぶ", key=f"pick_{profile.id}", use_container_width=True):
                    st.session_state["selected_profile_id"] = profile.id
                    st.rerun()


def get_selected_profile(profiles: list[MachineProfile]) -> MachineProfile | None:
    selected_id = st.session_state.get("selected_profile_id")
    return next((p for p in profiles if p.id == selected_id), None)
