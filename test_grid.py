import streamlit as st
import time

st.write('Test grid')
start = time.time()

st.markdown('''<style>
.blue-bg input { background-color: #d1ecf1 !important; font-weight: bold !important; font-size: 1.2em !important; }
.red-bg input { background-color: #f8d7da !important; font-size: 1.2em !important; }
.big-red { color: red; font-weight: bold; font-size: 1.2em; }
</style>''', unsafe_allow_html=True)

for i in range(30):
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.write(f'Pieza {i}')
    with c2: st.markdown(f'<span class=''big-red''>{i}</span>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class=''blue-bg''>', unsafe_allow_html=True)
        st.number_input('Buenas', key=f'b_{i}', label_visibility='collapsed')
        st.markdown('</div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class=''red-bg''>', unsafe_allow_html=True)
        st.number_input('Malas', key=f'm_{i}', label_visibility='collapsed')
        st.markdown('</div>', unsafe_allow_html=True)

st.write(f'Loaded in {time.time() - start:.2f}s')
