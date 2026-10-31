import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { PlusOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { createAdminUser, listAdminUsers, updateAdminUserRole, type AdminUser } from '../../api';
import { useAuthStore } from '../../stores';
import { t } from '../../i18n';

type FormValues = { username: string; password: string; nickname?: string; email?: string; role: AdminUser['role'] };

export function UserManagementPage() {
  const authUser = useAuthStore(s => s.authUser);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FormValues>();

  const load = async () => {
    setLoading(true);
    try { setUsers(await listAdminUsers()); } catch (error) { message.error((error as Error).message || t('加载用户失败')); } finally { setLoading(false); }
  };
  useEffect(() => { if (authUser?.can_manage_users) void load(); }, [authUser?.can_manage_users]);

  if (!authUser?.can_manage_users) {
    return <Alert type="error" showIcon message={t('没有用户管理权限')} description={t('请使用管理员账号登录。')} />;
  }

  const create = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try { await createAdminUser({ ...values, role: values.role || 'member' }); message.success(t('账号已创建')); form.resetFields(); setOpen(false); await load(); }
    catch (error) { message.error((error as Error).message || t('创建账号失败')); }
    finally { setSaving(false); }
  };

  return <div className="jx-settings-page" style={{ maxWidth: 980 }}>
    <div className="jx-settings-pageHeader">
      <div><h2 className="jx-settings-title"><SafetyCertificateOutlined /> {t('用户管理')}</h2><Typography.Paragraph type="secondary">{t('创建团队账号并设置管理员或普通成员角色。')}</Typography.Paragraph></div>
      <Space><Button icon={<ReloadOutlined />} onClick={() => void load()}>{t('刷新')}</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t('新建账号')}</Button></Space>
    </div>
    <Table rowKey="user_id" loading={loading} dataSource={users} pagination={{ pageSize: 10 }} columns={[
      { title: t('账号'), dataIndex: 'username' },
      { title: t('昵称'), dataIndex: 'nickname', render: (v: string | null) => v || '-' },
      { title: t('角色'), dataIndex: 'role', render: (role: AdminUser['role'], row: AdminUser) => <Select size="small" value={role} style={{ width: 130 }} disabled={row.user_id === authUser.user_id} onChange={async (next: AdminUser['role']) => { try { await updateAdminUserRole(row.user_id, next); message.success(t('角色已更新')); await load(); } catch (error) { message.error((error as Error).message || t('更新角色失败')); } }} options={[{ value: 'super_admin', label: t('管理员') }, { value: 'member', label: t('普通成员') }]} /> },
      { title: t('状态'), dataIndex: 'status', render: (status: string) => <Tag color={status === 'active' ? 'green' : 'default'}>{status === 'active' ? t('正常') : status}</Tag> },
    ]} />
    <Modal title={t('新建账号')} open={open} confirmLoading={saving} onCancel={() => setOpen(false)} onOk={() => void create()} okText={t('创建')}>
      <Form form={form} layout="vertical" initialValues={{ role: 'member' }}>
        <Form.Item name="username" label={t('登录账号')} rules={[{ required: true, message: t('请输入登录账号') }]}><Input autoComplete="off" /></Form.Item>
        <Form.Item name="password" label={t('初始密码')} rules={[{ required: true, min: 8, message: t('密码至少 8 位') }]}><Input.Password autoComplete="new-password" /></Form.Item>
        <Form.Item name="nickname" label={t('昵称')}><Input /></Form.Item>
        <Form.Item name="email" label={t('邮箱')}><Input /></Form.Item>
        <Form.Item name="role" label={t('角色')}><Select options={[{ value: 'member', label: t('普通成员') }, { value: 'super_admin', label: t('管理员') }]} /></Form.Item>
      </Form>
    </Modal>
  </div>;
}
